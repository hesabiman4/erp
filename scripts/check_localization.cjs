const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'..'),src=path.join(root,'frontend/src'),ts=require(path.join(root,'frontend/node_modules/typescript'));
const resources={fa:{},en:{},ps:{}};
const i18n={addResourceBundle:(lang,ns,copy)=>Object.assign(resources[lang]??={},copy),t:x=>x};
const cache={};
function load(file){
 file=path.resolve(src,file);if(!file.startsWith(src+path.sep))throw new Error('Catalog import outside frontend/src');if(!file.endsWith('.ts'))file+='.ts';if(cache[file])return cache[file];
 if(!fs.existsSync(file))return {};
 const module={exports:{}};cache[file]=module.exports;
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{module,exports:module.exports,require:name=>name==='./i18n'?{default:i18n}:load(name),Object});
 return module.exports;
}
load('localize');
const arabic=/[\u0600-\u06ff]/;
const literals=[];
for(const file of fs.readdirSync(src).filter(f=>/\.tsx?$/.test(f)&&!f.endsWith('-copy.ts')&&!['localize.ts','i18n.ts'].includes(f))){
 const source=ts.createSourceFile(file,fs.readFileSync(path.join(src,file),'utf8'),ts.ScriptTarget.Latest,true,file.endsWith('tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
 const variables={};
 function value(n){
  if(!n)return undefined;if(ts.isStringLiteralLike(n))return n.text;
  if(ts.isIdentifier(n))return variables[n.text];
  if(ts.isObjectLiteralExpression(n)){const result={};for(const p of n.properties){if(ts.isSpreadAssignment(p))Object.assign(result,value(p.expression));else if(ts.isPropertyAssignment(p)){const k=p.name.text,v=value(p.initializer);if(typeof v==='string')result[k]=v;}}return result;}
  return undefined;
 }
 function bundles(n){
  if(ts.isVariableDeclaration(n)&&ts.isIdentifier(n.name)){const v=value(n.initializer);if(v)variables[n.name.text]=v;}
  if(ts.isCallExpression(n)&&ts.isPropertyAccessExpression(n.expression)&&n.expression.name.text==='addResourceBundle'){
   const lang=value(n.arguments[0]),copy=value(n.arguments[2]);if(lang&&copy)Object.assign(resources[lang]??={},copy);
  }
  ts.forEachChild(n,bundles);
 }bundles(source);
 function strings(n){
  if(ts.isCallExpression(n)&&ts.isPropertyAccessExpression(n.expression)&&n.expression.name.text==='addResourceBundle')return;
  if(ts.isVariableDeclaration(n)&&ts.isObjectLiteralExpression(n.initializer??{})&&/^(en|ps|english|copy|translations)$/.test(n.name.text))return;
  if((ts.isStringLiteralLike(n)||ts.isJsxText(n))&&arabic.test(n.text)){
   if(!(ts.isPropertyAssignment(n.parent)&&n.parent.name===n))literals.push({file,line:source.getLineAndCharacterOfPosition(n.getStart()).line+1,text:n.text.trim().replace(/\s+/g,' '),kind:ts.SyntaxKind[n.kind]});
  }
  ts.forEachChild(n,strings);
 }strings(source);
}
// Explicit language-specific calendar abbreviations and numeric parser alphabets
// are not translatable interface prose. Their selection is checked in browsers.
const technical=new Set(['،','٬','٫','۰۱۲۳۴۵۶۷۸۹','٠١٢٣٤٥٦٧٨٩']);
const calendar=new Set(['کال / میاشت / ورځ','ش','ی','د','س','چ','پ','ج']);
const candidates=literals.filter(row=>!technical.has(row.text)&&!(row.file==='calendar-controls.tsx'&&calendar.has(row.text)));
const unique=[...new Set(candidates.map(row=>row.text))];
const missing={en:unique.filter(key=>!resources.en[key]),ps:unique.filter(key=>!resources.ps[key])};
const raw=[];
for(const file of fs.readdirSync(src).filter(file=>file.endsWith('.tsx'))){
 const sf=ts.createSourceFile(file,fs.readFileSync(path.join(src,file),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 function visit(node){
  if(ts.isJsxText(node)&&arabic.test(node.text))raw.push({file,line:sf.getLineAndCharacterOfPosition(node.getStart()).line+1,text:node.text.trim()});
  if(ts.isJsxAttribute(node)&&/^[a-z]/.test(node.parent.parent.tagName.getText(sf))&&['aria-label','aria-description','placeholder','alt','title'].includes(node.name.text)&&node.initializer&&ts.isStringLiteral(node.initializer)&&arabic.test(node.initializer.text))raw.push({file,line:sf.getLineAndCharacterOfPosition(node.getStart()).line+1,text:node.initializer.text});
  ts.forEachChild(node,visit);
 }visit(sf);
}
const result={checked_source_files:new Set(candidates.map(row=>row.file)).size,checked_unique_phrases:unique.length,catalog_counts:Object.fromEntries(Object.entries(resources).map(([lang,copy])=>[lang,Object.keys(copy).length])),missing,raw_visible_copy:raw,scope:'Static source phrases and native JSX translation hooks. Not runtime server messages, user data, printed PDFs or native editorial certification.'};
const report=process.argv.indexOf('--report');if(report>=0)fs.writeFileSync(path.resolve(root,process.argv[report+1]),JSON.stringify(result,null,2));
console.log(JSON.stringify(result,null,2));
if(missing.en.length||missing.ps.length||raw.length)process.exitCode=1;
