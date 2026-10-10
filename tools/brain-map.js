/* Actual module nodes and observed event deliveries. No simulated neural activity. */
window.MindMap=(()=>{
 const NS='http://www.w3.org/2000/svg',instances=new Map();
 const groups=[['senses','Sensory input',150,165,'#78c7ff'],['workspace','Attention & integration',450,165,'#b6a0ff'],['action','Action system',750,165,'#ffbf79'],['memory','Memory & identity',150,435,'#87d9d4'],['needs','Needs & outcome value',450,435,'#f09ca9'],['learning','Prediction & learning',750,435,'#a7dfa4']];
 const css=`.mind-observatory{position:relative;color:#dceaf1;font:13px system-ui,sans-serif}.mind-observatory .mind-top{display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap;color:#a9bccd;margin:10px 0}.mind-observatory svg.mind-network{width:100%;height:auto;max-height:none;display:block;background:radial-gradient(ellipse,#132437,#080f1c 75%);border:1px solid #2d4055;border-radius:18px}.mind-observatory .mind-node{cursor:pointer;outline:none}.mind-observatory .mind-node:hover circle,.mind-observatory .mind-node:focus circle{stroke:white;stroke-width:3}.mind-observatory .mind-node text{fill:#c5d8e4;font:12px system-ui;pointer-events:none}.mind-observatory .mind-node.is-selected text{fill:white;font-weight:700}.mind-observatory .mind-node.is-selected circle{stroke:white;stroke-width:2}.mind-observatory .mind-detail{padding:16px;margin-top:12px;border:1px solid #365166;background:#101e2b;border-radius:10px;min-height:115px;line-height:1.6}.mind-observatory .mind-detail h3{margin:0 0 5px;font-size:17px;color:#eef9ff}.mind-observatory .mind-detail p{margin:5px 0}.mind-observatory .mind-meta{font:11px ui-monospace,monospace;color:#a7c0d2;overflow-wrap:anywhere}.mind-observatory .mind-data{white-space:pre-wrap;max-height:240px;overflow:auto;font-size:11px}.mind-observatory .mind-tooltip{position:absolute;pointer-events:none;max-width:310px;padding:12px;border:1px solid #7898af;background:#101c2af5;color:#f3f7fa;border-radius:9px;box-shadow:0 8px 30px #0008;z-index:20;line-height:1.5;white-space:pre-line}.mind-observatory .mind-legend{display:flex;gap:15px;flex-wrap:wrap;font-size:11px;color:#c1d0dd;margin-top:10px}.mind-observatory .mind-note{color:#839cae;font-size:11px;margin-top:8px}.mind-observatory .mind-pulse{animation:mindPulse .8s ease-out}.mind-observatory .mind-flow{animation:mindFlow .8s ease-out}@keyframes mindPulse{0%{r:12;filter:drop-shadow(0 0 8px currentColor)}100%{r:7;filter:none}}@keyframes mindFlow{0%{stroke-opacity:.9;stroke-dashoffset:22}100%{stroke-opacity:.12;stroke-dashoffset:0}}@media(prefers-reduced-motion:reduce){.mind-observatory *{animation:none!important}}`;
 function arrangement(width){const columns=width<480?1:width<800?2:3;return {width:columns*300,height:Math.ceil(groups.length/columns)*270+70,groups:groups.map((g,index)=>[g[0],g[1],150+(index%columns)*300,165+Math.floor(index/columns)*270,g[4]])}}
 function svg(tag,attrs={}){const e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);return e}
 function div(cls,text){const e=document.createElement('div');e.className=cls;if(text)e.textContent=text;return e}
 function mount(id){const root=document.getElementById(id);if(!root||instances.has(id))return;
  if(!document.getElementById('mind-observatory-style')){const style=document.createElement('style');style.id='mind-observatory-style';style.textContent=css;document.head.append(style)}
  root.replaceChildren();root.classList.add('mind-observatory');
  const top=div('mind-top'),status=div('','Waiting for telemetry'),hint=div('','Hover to understand · click to inspect');top.append(status,hint);
  const arranged=arrangement(root.closest('.brain-panel')?900:root.clientWidth);
  const network=svg('svg',{viewBox:`0 0 ${arranged.width} ${arranged.height}`,class:'mind-network',role:'group','aria-label':'Actual software modules grouped by function; lines show observed message deliveries'});
  const outline=svg('path',{d:'M445 30 C360 -5 280 15 250 40 C115 15 45 80 30 180 C-5 275 22 385 75 435 C65 550 230 603 330 570 C380 600 423 570 447 550 L465 585 L490 552 C555 600 660 578 700 550 C820 560 889 440 875 370 C920 280 895 170 850 120 C818 27 665 -2 590 35 C530 1 480 10 460 32',fill:'#122032','fill-opacity':'.55',stroke:'#547189','stroke-opacity':'.35','stroke-width':2});if(arranged.width===900)network.append(outline);
  network.append(svg('path',{d:'M450 35 C430 170 470 320 450 565',fill:'none',stroke:'#698099','stroke-opacity':'.18','stroke-dasharray':'5 10'}));
  for(const [key,label,x,y,color]of arranged.groups){network.append(svg('rect',{x:x-131,y:y-118,width:262,height:232,rx:25,fill:'#112031','fill-opacity':'.8',stroke:color,'stroke-opacity':'.2'}));const t=svg('text',{x:x-109,y:y-88,fill:color,'font-size':16,'font-family':'system-ui','font-weight':600});t.textContent=label;network.append(t)}
  const links=svg('g'),nodes=svg('g');network.append(links,nodes);
  const detail=div('mind-detail');detail.innerHTML='<h3>Explore the module system</h3><p>Each dot is an actual registered module. Hover or focus a dot for a plain-English explanation; select it to keep its evidence visible.</p>';
  const legend=div('mind-legend');for(const [label,color]of [['● Input received','#78c7ff'],['● State changed','#ffd479'],['● Output emitted','#70ffcd']]){const item=document.createElement('span');item.textContent=label;item.style.color=color;legend.append(item)}
  const note=div('mind-note','Brain-shaped layout, not biological anatomy. Links are recorded deliveries, not proof of influence. No activity is invented when offline.');
  const tip=div('mind-tooltip');tip.hidden=true;root.append(top,network,legend,note,detail,tip);
  instances.set(id,{groups:arranged.groups,root,status,network,links,nodes,detail,tip,layout:new Map(),prior:{},routePrior:{},selected:null,health:{},activity:{},state:{},online:false});
 }
 function inspect(i,name){const meta=i.activity.modules?.[name]||{label:name,description:'Inspect the raw event record for details.'};const h=i.health[name]||{},last=i.activity.latest?.[name];
  const rawWasOpen=!!i.detail.querySelector('details')?.open;
  i.detail.replaceChildren();const title=document.createElement('h3');title.textContent=meta.label;
  const desc=document.createElement('p');desc.textContent=meta.description;
  const technical=div('mind-meta',`${name} · ${h.processed||0} inputs · ${h.outputs||0} emitted outputs · ${h.changes||0} state changes · ${h.failures||0} errors`);
  const event=document.createElement('p');event.textContent=last?`Last received: ${last.kind} from ${last.source}. ${new Date(last.timestamp).toLocaleTimeString()}.`:'No recent delivered event in the bounded activity window.';
  const raw=document.createElement('details'),summary=document.createElement('summary'),data=document.createElement('pre');raw.open=rawWasOpen;summary.textContent='Actual telemetry and event reference';data.className='mind-data';data.textContent=JSON.stringify({module:name,health:h,last_event:last||null},null,2);raw.append(summary,data);i.detail.append(title,desc,technical,event,raw);
  for(const [n,node]of i.layout)node.element.classList.toggle('is-selected',n===name);
 }
 function layout(i,names){const signature=names.join('|');if(i.signature===signature)return;i.signature=signature;i.nodes.replaceChildren();i.layout.clear();
  for(const [key,,x,y,color]of i.groups){const members=names.filter(n=>(groups.some(g=>g[0]===i.activity.modules?.[n]?.group)?i.activity.modules[n].group:'memory')===key);members.forEach((name,index)=>{
   const px=x-106,py=y-52+index*27;const g=svg('g',{class:'mind-node',tabindex:0,role:'button','aria-label':i.activity.modules[name]?.label||name});
   const dot=svg('circle',{cx:px,cy:py,r:7,fill:'#254356',stroke:color,'stroke-opacity':'.65'}),text=svg('text',{x:px+16,y:py+4});text.textContent=i.activity.modules[name]?.label||name.replaceAll('_',' ');const hit=svg('rect',{x:px-12,y:py-13,width:236,height:26,fill:'transparent'});g.append(hit,dot,text);i.nodes.append(g);i.layout.set(name,{x:px,y:py,element:g,dot});
   const show=e=>{const meta=i.activity.modules[name];i.tip.textContent=(meta?.label||name)+'\n'+(meta?.description||'')+'\nModule: '+name;i.tip.hidden=false;const box=i.root.getBoundingClientRect(),rect=g.getBoundingClientRect();i.tip.style.left=Math.max(0,Math.min(box.width-320,(e.clientX||rect.left)-box.left+12))+'px';i.tip.style.top=Math.max(0,(e.clientY||rect.bottom)-box.top+16)+'px'};
   g.addEventListener('pointerenter',show);g.addEventListener('focus',show);g.addEventListener('pointerleave',()=>i.tip.hidden=true);g.addEventListener('blur',()=>i.tip.hidden=true);
   const select=()=>{i.selected=name;i.tip.hidden=true;inspect(i,name)};g.addEventListener('click',select);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select()}});
  })}
 }
 function update(health,online,activity={},state={}){for(const i of instances.values()){
  i.health=health||{};i.activity=activity||{};i.state=state||{};i.online=!!online;
  const names=Object.keys(i.activity.modules||i.health).sort();layout(i,names);
  i.status.textContent=`${online?'LIVE':'OFFLINE / last recorded state'} · ${names.length} modules · ${i.activity.window_events||0} recent events${state['brain.busy']?' · model working':''}`;
  for(const [name,node]of i.layout){const h=i.health[name]||{},old=i.prior[name],last=i.activity.latest?.[name];const fresh=last&&Date.now()-Date.parse(last.timestamp)<4000;
   const changed=old&&h.processed!==old.processed;const output=old&&(h.outputs||0)>(old.outputs||0);const writes=old&&(h.changes||0)>(old.changes||0);const emitted=(i.activity.recent||[]).some(e=>e.source===name&&Date.now()-Date.parse(e.timestamp)<2000);
   const color=output||emitted?'#70ffcd':writes?'#ffd479':'#78c7ff';const active=online&&(fresh&&(changed||!old)||emitted);
   node.dot.setAttribute('fill',active?color:'#254356');node.dot.style.color=color;node.dot.classList.remove('mind-pulse');if(active){void node.dot.getBoundingClientRect();node.dot.classList.add('mind-pulse')}
  }
  i.links.replaceChildren();for(const route of i.activity.routes||[]){const a=i.layout.get(route.source),b=i.layout.get(route.target);if(!a||!b)continue;const fresh=online&&Date.now()-Date.parse(route.timestamp)<4000,key=route.source+'|'+route.target;const path=svg('path',{d:`M${a.x} ${a.y} C${a.x+55} ${a.y},${b.x-55} ${b.y},${b.x} ${b.y}`,fill:'none',stroke:fresh?'#69e1d0':'#6b8aab','stroke-width':fresh?1.5:1,'stroke-opacity':fresh?.35:.08,'stroke-dasharray':'4 7'});const title=svg('title');title.textContent=`${route.source} → ${route.target}: ${route.kind} (${route.count} deliveries in sampled events)`;path.append(title);if(fresh&&i.routePrior[key]!==route.event_id)path.classList.add('mind-flow');i.links.append(path);i.routePrior[key]=route.event_id}
  if(i.selected)inspect(i,i.selected);i.prior=JSON.parse(JSON.stringify(i.health));
 }}
 return {mount,update};
})();
