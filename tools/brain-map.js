/* A schematic of software modules, not brain anatomy or a consciousness meter. */
window.MindMap=(()=>{
 const groups=[
  ['Senses',/perception|sensory|minecraft_body|salience/,'M145 24 Q70 15 39 70 L128 112 L158 86 Z'],
  ['Memory',/memory|recall|consolidat|reflection/,'M35 80 Q0 126 39 184 L121 164 L126 121 Z'],
  ['Needs',/homeostasis|motivation|survival_(food|sleep|threat|construction|exploration)/,'M41 194 Q72 246 150 237 L159 187 L122 174 Z'],
  ['Workspace',/workspace|arbiter|deliberation|planner/,'M174 23 Q248 13 281 72 L199 113 L166 85 Z'],
  ['Action',/motor|executive|outbox|critic/,'M289 80 Q321 135 279 190 L202 165 L200 122 Z'],
  ['Learning',/muscle_learning|consequence|adaptive_feedback|survival_outcome|prediction/,'M274 198 Q243 247 172 237 L166 188 L200 175 Z']
 ];
 let previous={},mounted=new Set();
 function mount(id){const el=document.getElementById(id);if(!el||mounted.has(id))return;mounted.add(id);
  el.innerHTML='<div class="brain-layout"><svg viewBox="0 0 320 260" role="img" aria-label="Schematic of software module activity"><path d="M155 92 L131 121 L137 161 L159 183 L193 161 L192 122 Z" fill="#152c44" stroke="#6ab6c9"/>'+groups.map(([label,,path],i)=>'<path data-region="'+i+'" d="'+path+'" fill="#19394c" stroke="#5a99a8" stroke-width="2"><title>'+label+'</title></path>').join('')+'<path d="M160 25 V233 M46 131 H276" stroke="#6db5bd" opacity=".25" stroke-dasharray="3 5"/></svg><div class="brain-legend">'+groups.map(([name],i)=>'<div data-legend="'+i+'">● '+name+'</div>').join('')+'</div></div><small>Real module events · schematic, not a brain scan</small>';
 }
 function update(health,online){let changed={};for(const [name,h]of Object.entries(health||{})){if(previous[name]&&previous[name]!==h.last_event)changed[name]=true;previous[name]=h.last_event}
  for(const id of mounted){const el=document.getElementById(id);groups.forEach(([label,pattern],i)=>{const active=online&&Object.keys(changed).some(n=>pattern.test(n));const region=el.querySelector('[data-region="'+i+'"]'),legend=el.querySelector('[data-legend="'+i+'"]');if(active){region.animate([{fill:'#70ffcd',filter:'drop-shadow(0 0 7px #54ddbf)'},{fill:'#19394c',filter:'none'}],{duration:1200});legend.animate([{color:'#70ffcd'},{color:'#9cb9c8'}],{duration:1200})}region.querySelector('title').textContent=label+': '+Object.keys(health||{}).filter(n=>pattern.test(n)).join(',')})}
 }
 return {mount,update};
})();
