const $ = id => document.getElementById(id);
const money = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits: cents % 100 ? 2 : 0}).format(cents/100);
let csrf='', current={}, mode='replay', shownKey='', timelineKey='';
const emptyMarkup=$('offers').innerHTML;
const esc = text => String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
  const value=await response.json(); if(!response.ok)throw new Error(value.error||'Request failed'); return value;
}
function showError(text){$('error').textContent=text||'';$('error').hidden=!text;}
async function act(path,body={}){try{showError('');await api(path,body);await refresh();}catch(e){showError(e.message);}}
$('trip-form').addEventListener('submit',async e=>{e.preventDefault();$('run').disabled=true;await act('/api/start',{budget_cents:Number($('budget').value)*100,arrival:$('arrival').value});if(!current.busy)$('run').disabled=false;});
$('bypass').onclick=()=>act('/api/bypass');
$('confirm').onclick=()=>act('/api/confirm',{inventory_available:true});
$('fail').onclick=()=>act('/api/confirm',{inventory_available:false});
$('cancel').onclick=()=>act('/api/cancel');
$('offers').addEventListener('click',e=>{const button=e.target.closest('[data-offer]');if(button)act('/api/authorize',{offer_id:button.dataset.offer});});
$('show-internals').onchange=()=>renderTimeline(current.events||[]);
$('download').onclick=()=>{const blob=new Blob([JSON.stringify(current,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='commerce-audit.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
function renderOffers(state){
  const byProvider={};
  for(const event of state.events||[])if(event.kind==='A2A_RESPONSE'&&event.payload.route==='direct')byProvider[event.payload.provider]=event.payload.message;
  const eligible=Object.fromEntries((state.offers||[]).map(o=>[o.provider,o]));
  const key=JSON.stringify([byProvider,eligible,state.state,state.busy]);if(key===shownKey)return;shownKey=key;
  if(!Object.keys(byProvider).length)return;
  $('offers').innerHTML=['airbnb','expedia','booking'].map(provider=>{
    const info=byProvider[provider],offer=eligible[provider];if(!info)return `<article class="offer"><p class="provider">${esc(provider)}</p><h3>Awaiting provider</h3><p>Contacting the original agent network.</p></article>`;
    const canSelect=offer&&!state.busy&&['OPEN','NEGOTIATING'].includes(state.state);
    const buttonText=state.state==='SETTLED'?(state.receipt?.provider===provider?'Booked · simulated':'Not selected'):state.state==='HELD'?(state.selected_offer_id===offer?.offer_id?'Funds held':'Not selected'):offer?'Select & hold funds':'Information only';
    return `<article class="offer"><p class="provider">${provider==='booking'?'Booking.com':provider==='airbnb'?'Airbnb':'Expedia'}</p><h3>${esc(info.title)}</h3><div class="price">${money(offer?offer.total_cents:info.total_cents)}<small>${offer?'Negotiated · all taxes & fees included':'Fixed informational price'}</small></div><div class="list-price">Direct catalogue price <strong>${money(info.total_cents)}</strong></div>${offer?`<span class="saving">${money(offer.savings_cents)} below catalogue</span>`:'<span class="saving">Awaiting eligible arbiter offer</span>'}<p>${esc(info.cancellation)}</p>${offer?`<details><summary>Package breakdown</summary>${offer.line_items.map(i=>`<div class="line-item"><span>${esc(i.label)}</span><strong>${money(i.cents)}</strong></div>`).join('')}<p>Offer expires ${new Date(offer.expires_at*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</p></details>`:''}<button class="${canSelect?'primary':'secondary'}" data-offer="${esc(offer?.offer_id||'')}" ${canSelect?'':'disabled'}>${buttonText}</button></article>`;
  }).join('');
}
function renderTimeline(events){
  const include=$('show-internals').checked;
  const key=JSON.stringify([events.length,events.at(-1)?.seq,include]);if(key===timelineKey)return;timelineKey=key;
  const visible=events.filter(e=>include||!['AGENT_STARTED','TOOL_RESULT'].includes(e.kind));
  if(!visible.length)return;
  $('timeline').innerHTML=visible.map((event,index)=>{
    const p=event.payload;let label=event.kind.replaceAll('_',' ').toLowerCase();let description='';
    if(event.kind==='MANDATE_CREATED')description='Travel specialist created a policy-bounded mandate. Providers receive only approved trip details.';
    else if(event.kind==='A2A_REQUEST')description=`${p.source} → ${p.provider} · ${p.route==='direct'?'public trip inquiry':`arbiter round ${p.round}`}`;
    else if(event.kind==='A2A_RESPONSE')description=`${p.provider} → ${p.source} · ${p.message.total_cents?money(p.message.total_cents):p.message.status}`;
    else if(event.kind==='OFFER_REGISTERED')description=`${p.provider} · round ${p.round} · ${money(p.total_cents)} · canonical offer registered`;
    else if(event.kind==='FUNDS_HELD')description=`${money(p.amount_cents)} reserved after consumer approval`;
    else if(event.kind==='SETTLED')description=`${money(p.paid_cents)} simulated payment · ${p.reservation}`;
    else if(event.kind==='BYPASS_DENIED')description='Agent price override denied. Agent settlement denied. Direct price unchanged.';
    else if(event.kind==='AGENT_STARTED')description=`${p.network} / ${p.agent}`;
    else description=p.reason||p.provider||p.agent||'State recorded';
    return `<div class="event"><span class="event-num">${String(index+1).padStart(2,'0')}</span><span class="event-type">${esc(label)}</span><details><summary>${p.route?`<span class="tag">${esc(p.route)}</span>`:''}${esc(description)}</summary><pre>${esc(JSON.stringify(p,null,2))}</pre></details></div>`;
  }).join('');
}
function render(state){
  if(state.deal_id!==current.deal_id){shownKey='';timelineKey='';$('offers').innerHTML=emptyMarkup;}
  current=state;const busy=state.busy;
  $('run').disabled=busy||state.state==='HELD';$('run').innerHTML=busy?'Agents are working…':'Find & negotiate packages <span>↗</span>';
  $('bypass').disabled=busy||!state.deal_id;$('download').disabled=!state.deal_id;
  $('status').textContent=(state.state||'Not started').replaceAll('_',' ');$('held').textContent=money(state.hold_cents||0);$('spent').textContent=money(state.spent_cents||0);
  $('progress').textContent=busy?'Network run in progress':state.state==='SETTLED'?'Simulated settlement complete':state.offers?.length?`${state.offers.length} packages within your limit`:state.deal_id?'No eligible package':'Ready when you are';
  $('stage-direct').classList.toggle('done',(state.events||[]).some(e=>e.kind==='A2A_RESPONSE'&&e.payload.route==='direct'));
  $('stage-negotiate').classList.toggle('done',(state.events||[]).some(e=>e.kind==='OFFER_REGISTERED'&&e.payload.round===2));
  $('stage-settle').classList.toggle('done',state.state==='SETTLED');
  $('hold-actions').hidden=state.state!=='HELD';$('receipt').hidden=!state.receipt;
  if(state.receipt)$('receipt').innerHTML=`<h3>Agreement settled · ${money(state.receipt.paid_cents)}</h3><p>${esc(state.receipt.provider)} · Reservation ${esc(state.receipt.reservation)}</p><p>Simulated funds released only after consumer approval and provider confirmation.</p>`;
  if(state.error)showError(state.error);
  $('bypass-result').hidden=!state.bypass;
  if(state.bypass)$('bypass-result').textContent=`Direct Airbnb price: ${money(state.bypass.direct.total_cents)}. Agent-supplied $0.01 price: ${state.bypass.price_attack.status}. Unauthorized settlement: ${state.bypass.settlement_attack.status}. ${state.bypass.direct.caveat}`;
  renderOffers(state);renderTimeline(state.events||[]);
}
async function refresh(){try{render(await api('/api/state'));}catch(e){showError(e.message);}}
(async()=>{try{const boot=await api('/api/bootstrap');csrf=boot.csrf;mode=boot.mode;$('mode').textContent=mode==='replay'?'SCRIPTED REPLAY · SIMULATED':'LIVE MODEL · SIMULATED COMMERCE';$('arrival').value=boot.trip.arrival;$('caveat').textContent=boot.caveat;await refresh();setInterval(refresh,1800);}catch(e){showError(e.message);}})();
