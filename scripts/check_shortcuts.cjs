/** Guard runtime source and visible hints against reserved window-close keys. */
const fs=require('node:fs');const path=require('node:path');
const root=path.resolve(__dirname,'../frontend/src');const bad=[];let checked=0;
function scan(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,item.name);if(item.isDirectory())scan(file);else if(/\.[cm]?[jt]sx?$/.test(file)){checked++;const lines=fs.readFileSync(file,'utf8').split(/\r?\n/);lines.forEach((line,i)=>{if(/alt\s*\+\s*f4|['"`]f4['"`]/i.test(line))bad.push(path.relative(root,file)+':'+(i+1));});}}}
scan(root);console.log(JSON.stringify({checked_source_files:checked,forbidden_window_shortcuts:bad}));if(bad.length)process.exitCode=1;
