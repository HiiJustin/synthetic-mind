/* A schematic of software modules, not brain anatomy or a consciousness meter. */
window.MindMap=(()=>{
 const groups=[
  ['Senses',/perception|sensory|minecraft_body|salience|input_scene|embodiment/,'M145 24 Q70 15 39 70 L128 112 L158 86 Z'],
  ['Memory',/memory|recall|consolidat|reflection/,'M35 80 Q0 126 39 184 L121 164 L126 121 Z'],
  ['Needs',/homeostasis|motivation|subconscious_reward|survival_(food|sleep|threat|construction|exploration)/,'M41 194 Q72 246 150 237 L159 187 L122 174 Z'],
  ['Workspace',/workspace|arbiter|deliberation|planner|goal_memory/,'M174 23 Q248 13 281 72 L199 113 L166 85 Z'],
  ['Action',/motor|executive|outbox|critic|action_selection/,'M289 80 Q321 135 279 190 L202 165 L200 122 Z'],
  ['Learning',/muscle_learning|consequence|adaptive_feedback|survival_outcome|prediction|world_model/,'M274 198 Q243 247 172 237 L166 188 L200 175 Z']
 ];
 let previous={},mounted=new Set();
 function mount(id){const el=document.getElementById(id);if(!el||mounted.has(id))return;mounted.add(id);
  el.innerHTML='<div class="brain-layout"><svg viewBox="0 0 320 260" role="img" aria-label="Schematic of software module activity"><path d="M155 92 L131 121 L137 161 L159 183 L193 161 L192 122 Z" fill="#152c44" stroke="#6ab6c9"/>'+groups.map(([label,,path],i)=>'<path data-region="'+i+'" d="'+path+'" fill="#19394c" stroke="#5a99a8" stroke-width="2"><title>'+label+'</title></path>').join('')+'<path d="M160 25 V233 M46 131 H276" stroke="#6db5bd" opacity=".25" stroke-dasharray="3 5"/></svg><div class="brain-legend">'+groups.map(([name],i)=>'<div data-legend="'+i+'">● '+name+'</div>').join('')+'</div></div><small>Outputs / state changes / inputs · software activity</small>';
 }
 function update(health,online){
  for(const id of mounted){const el=document.getElementById(id);groups.forEach(([label,pattern],i)=>{
   const entries=Object.entries(health||{}).filter(([n])=>pattern.test(n));
   const changed=entries.filter(([n,h])=>previous[n]&&h.processed!==previous[n].processed);
   const outputs=changed.some(([n,h])=>(h.outputs||0)>(previous[n].outputs||0));
   const writes=changed.some(([n,h])=>(h.changes||0)>(previous[n].changes||0));
   const color=outputs?'#70ffcd':writes?'#ffd479':'#659dc8';
   const region=el.querySelector('[data-region="'+i+'"]');
   if(online&&changed.length)region.animate([{fill:color},{fill:'#19394c'}],{duration:650});
   const detail=label+'\n'+entries.map(([n,h])=>n+': '+h.processed+' inputs / '+(h.outputs||0)+' outputs / '+(h.changes||0)+' changes; last '+h.last_kind).join('\n');
   region.querySelector('title').textContent=detail;
   region.style.cursor='pointer';region.onclick=()=>{let box=el.querySelector('pre');if(!box){box=document.createElement('pre');box.style.whiteSpace='pre-wrap';el.append(box)}box.textContent=detail};
  })}
  previous=JSON.parse(JSON.stringify(health||{}));
 }
 return {mount,update};
})();
