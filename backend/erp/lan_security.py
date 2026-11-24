"""Private installation TLS material. No HTTP, Django, stock or journal side effects."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import uuid
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def database_tag(name):
    return hashlib.sha256(str(name).encode()).hexdigest()[:12]


def configuration_path(root, database):
    return Path(root)/'.local'/f'lan-settings-{database_tag(database)}.json'


def read_configuration(root, database):
    try:
        value=json.loads(configuration_path(root,database).read_text(encoding='utf8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def lan_address(value):
    try:address=ipaddress.IPv4Address(value)
    except (ValueError,TypeError):raise ValueError('Choose a private LAN IPv4 address.')
    # Explicit RFC1918 only; excludes loopback, link-local, public and wildcard binds.
    if not any(address in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('Choose a private LAN IPv4 address.')
    return str(address)


def lan_port(value):
    if isinstance(value,bool) or not str(value).isascii() or not str(value).isdigit() or not 1024<=int(value)<=65535:
        raise ValueError('Choose a port from1024 to65535.')
    return int(value)


def local_addresses():
    values=set()
    for name in {socket.gethostname(),socket.getfqdn()}:
        try:
            for record in socket.getaddrinfo(name,None,socket.AF_INET):
                try:values.add(lan_address(record[4][0]))
                except ValueError:pass
        except OSError:pass
    return sorted(values)


def private_directory(folder):
    folder.mkdir(parents=True,exist_ok=False,mode=0o700)
    if os.name=='nt':
        result=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True)
        sid=next(csv.reader(result.stdout.strip().splitlines()))[1]
        subprocess.run(['icacls',str(folder),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],capture_output=True,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    else:folder.chmod(0o700)


def material(root,config):
    revision=str(config.get('revision',''))
    if len(revision)!=32 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('Configure LAN HTTPS first.')
    folder=Path(root)/'.local'/'tls'/revision
    if folder.is_symlink() or not folder.resolve().is_relative_to((Path(root)/'.local'/'tls').resolve()):raise ValueError('Invalid TLS storage.')
    return folder


def certificate_summary(root,config):
    folder=material(root,config)
    ca=x509.load_pem_x509_certificate((folder/'ca.crt').read_bytes())
    cert=x509.load_pem_x509_certificate((folder/'server.crt').read_bytes())
    address=lan_address(config['address']);port=lan_port(config['port'])
    if ipaddress.ip_address(address) not in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress):raise ValueError('The LAN certificate does not match the selected address.')
    now=datetime.now(timezone.utc)
    if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc or not ca.not_valid_before_utc<=now<ca.not_valid_after_utc:raise ValueError('The LAN certificate has expired. Renew it locally.')
    return {'address':address,'port':port,'url':f'https://{address}:{port}/','expires_at':cert.not_valid_after_utc.isoformat(),'ca_sha256':ca.fingerprint(hashes.SHA256()).hex(),'phone_trust_verified':False,'physical_device_verified':False}


def configure(root,database,address,port):
    address=lan_address(address);port=lan_port(port)
    # Verify that this machine can bind the requested interface; never open a listener here.
    with socket.socket(socket.AF_INET) as probe:probe.bind((address,0))
    old=read_configuration(root,database);now=datetime.now(timezone.utc)
    ca_key=None
    if old:
        old_folder=material(root,old)
        ca=x509.load_pem_x509_certificate((old_folder/'ca.crt').read_bytes())
        if ca.not_valid_after_utc<now+timedelta(days=366):raise ValueError('The local certificate authority needs operator renewal.')
        ca_key=serialization.load_pem_private_key((old_folder/'ca.key').read_bytes(),password=None)
    else:
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Nawa ERP private LAN '+database_tag(database))])
        ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=3650)).add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False).add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True).sign(ca_key,hashes.SHA256()))
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    cert=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,address)])).issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365)).add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False).add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False).add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),critical=True).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]),critical=False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(ca_key,hashes.SHA256()))
    config={'revision':uuid.uuid4().hex,'address':address,'port':port,'configured_at':now.isoformat()}
    folder=material(root,config);private_directory(folder)
    for name,value in [('ca.key',ca_key),('server.key',key)]:
        (folder/name).write_bytes(value.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        if os.name!='nt':(folder/name).chmod(0o600)
    (folder/'ca.crt').write_bytes(ca.public_bytes(serialization.Encoding.PEM));(folder/'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    path=configuration_path(root,database);temp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(config),encoding='utf8');temp.replace(path)
    return config
