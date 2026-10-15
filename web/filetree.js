(function(root){'use strict';
function build(records){const tree={key:'',name:'',dirs:new Map(),files:[]};for(const r of records){const parts=(r.path||r.full_path||r.name).split('/').filter(Boolean);parts.pop();let p=tree;for(const name of parts){const key=p.key+'/'+name;if(!p.dirs.has(name))p.dirs.set(name,{key,name,dirs:new Map(),files:[]});p=p.dirs.get(name);}p.files.push(r);}return tree;}
function ancestors(record){const p=(record.path||record.full_path||record.name).split('/').filter(Boolean);p.pop();return p.map((_,i)=>'/'+p.slice(0,i+1).join('/'));}
const api={build,ancestors};if(typeof module!=='undefined')module.exports=api;else root.EPFileTree=api;
})(globalThis);
