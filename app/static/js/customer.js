const DraftStore = (() => {
  const KEY = 'cateringDraftV1';
  const blank = () => ({details:{}, item_ids:[], requested_dishes:[], customer_notes:'', last_updated:null});
  const load = () => {
    try {
      const d=JSON.parse(localStorage.getItem(KEY)) || blank();
      d.details=d.details||{}; d.item_ids=Array.isArray(d.item_ids)?d.item_ids:[]; d.requested_dishes=Array.isArray(d.requested_dishes)?d.requested_dishes:[]; d.customer_notes=String(d.customer_notes||'');
      return d;
    } catch { return blank(); }
  };
  const save = (draft) => { draft.last_updated = new Date().toISOString(); localStorage.setItem(KEY, JSON.stringify(draft)); window.dispatchEvent(new CustomEvent('draftchange', {detail:draft})); };
  const clear = () => { localStorage.removeItem(KEY); window.dispatchEvent(new CustomEvent('draftchange', {detail:blank()})); };
  const setDetails = (details) => { const d=load(); d.details=details; save(d); return d; };
  const toggleItem = (id) => { const d=load(); const n=Number(id); d.item_ids = d.item_ids.includes(n) ? d.item_ids.filter(x=>x!==n) : [...d.item_ids,n]; save(d); return d; };
  const removeItem = (id) => { const d=load(); d.item_ids=d.item_ids.filter(x=>x!==Number(id)); save(d); return d; };
  const setRequestedDishes = (dishes) => { const d=load(); d.requested_dishes=dishes; save(d); return d; };
  const setCustomerNotes = (notes) => { const d=load(); d.customer_notes=String(notes||''); save(d); return d; };
  return {load,save,clear,setDetails,toggleItem,removeItem,setRequestedDishes,setCustomerNotes};
})();
window.DraftStore = DraftStore;

function initDetailsForm(){
  const form=document.querySelector('[data-details-form]'); if(!form) return;
  const draft=DraftStore.load();
  Object.entries(draft.details||{}).forEach(([k,v])=>{ const el=form.elements[k]; if(el && !['submit'].includes(el.type)) el.value=v ?? ''; });
  const same=document.getElementById('same-whatsapp');
  const phone=form.elements.phone, wa=form.elements.whatsapp;
  const dateInput=form.elements.event_date, timeInput=form.elements.event_time;
  const errorBox=document.querySelector('[data-details-error]');

  const minimumEventDateTime=()=>new Date(Date.now()+24*60*60*1000);
  const toDateInput=(d)=>{
    const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), day=String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${day}`;
  };
  if(dateInput) dateInput.min=toDateInput(minimumEventDateTime());

  document.querySelectorAll('[data-picker-button]').forEach(btn=>btn.addEventListener('click',()=>{
    const input=document.getElementById(btn.dataset.pickerButton);
    if(!input) return;
    if(typeof input.showPicker==='function'){ try{ input.showPicker(); }catch{} } else { input.focus(); input.click(); }
  }));
  document.querySelectorAll('[data-native-picker]').forEach(input=>input.addEventListener('click',()=>{
    if(typeof input.showPicker==='function'){ try{ input.showPicker(); }catch{} }
  }));

  if(phone && wa && phone.value && phone.value===wa.value) same.checked=true;
  same?.addEventListener('change',()=>{ if(same.checked) wa.value=phone.value; });
  phone?.addEventListener('input',()=>{ if(same?.checked) wa.value=phone.value; });

  function showDetailsError(message,field){
    if(errorBox){ errorBox.textContent=message; errorBox.hidden=false; } else alert(message);
    const target=field&&form.elements[field];
    target?.focus();
  }

  form.addEventListener('submit',(e)=>{
    e.preventDefault();
    if(errorBox) errorBox.hidden=true;
    if(!form.reportValidity()) return;
    const fd=new FormData(form); const details={};
    ['name','phone','whatsapp','event_date','event_name','event_time','adults','kids','address','eircode'].forEach(k=>details[k]=String(fd.get(k)||'').trim());
    if((Number(details.adults)||0)+(Number(details.kids)||0)<1){ showDetailsError('Enter at least one guest in Adults or Kids.','adults'); return; }
    const eventDateTime=new Date(`${details.event_date}T${details.event_time}:00`);
    if(!Number.isFinite(eventDateTime.getTime()) || eventDateTime.getTime()<minimumEventDateTime().getTime()){
      showDetailsError('Please choose an event date and time at least 24 hours from now.','event_date');
      return;
    }
    DraftStore.setDetails(details);
    location.href=form.dataset.next||'/menu';
  });
}

function formatCount(n){return `${n} item${n===1?'':'s'} selected`;}

function initMenu(){
  const root=document.querySelector('[data-menu-root]'); if(!root) return;
  const data=JSON.parse(document.getElementById('menu-data').textContent||'[]');
  const menuBtns=[...document.querySelectorAll('[data-menu-choice]')];
  const dietBtns=[...document.querySelectorAll('[data-diet-choice]')];
  const categoryTabs=document.querySelector('[data-category-tabs]');
  const content=document.querySelector('[data-menu-content]');
  const requestDialog=document.querySelector('[data-request-dialog]');
  const requestInput=document.querySelector('[data-request-input]');
  const requestCount=document.querySelector('[data-request-count]');
  let selectedMenu=data[0]?.id || null;
  let selectedDiet='combo';
  let activeCategory=null;

  const itemMap=new Map();
  data.forEach(m=>m.categories.forEach(c=>c.subcategories.forEach(s=>s.items.forEach(i=>itemMap.set(i.id,{...i,menu:m.name,category:c.name,subcategory:s.name})))))
  window.__menuItemMap=itemMap;

  function updateRequestCount(){
    const n=DraftStore.load().requested_dishes.length;
    if(requestCount) requestCount.textContent=n?`(${n})`:'';
  }
  document.querySelector('[data-open-request-dialog]')?.addEventListener('click',()=>{
    const d=DraftStore.load(); requestInput.value=d.requested_dishes.join('\n'); requestDialog?.showModal();
  });
  document.querySelector('[data-save-requests]')?.addEventListener('click',()=>{
    const lines=String(requestInput?.value||'').split(/\r?\n/).map(x=>x.replace(/\s+/g,' ').trim()).filter(Boolean);
    const unique=[]; const seen=new Set();
    for(const line of lines){ const key=line.toLowerCase(); if(!seen.has(key)){seen.add(key);unique.push(line.slice(0,180));} }
    if(unique.length>20){ alert('Please request no more than 20 extra dishes.'); return; }
    DraftStore.setRequestedDishes(unique); updateRequestCount(); requestDialog?.close();
  });
  requestDialog?.addEventListener('click',(e)=>{ if(e.target===requestDialog) requestDialog.close(); });

  function render(){
    const m=data.find(x=>x.id===selectedMenu); if(!m){ content.innerHTML='<div class="empty">No active menus yet.</div>'; return; }
    menuBtns.forEach(b=>b.classList.toggle('active',Number(b.dataset.menuChoice)===selectedMenu));
    dietBtns.forEach(b=>b.classList.toggle('active',b.dataset.dietChoice===selectedDiet));
    const visibleCats=m.categories.map(c=>({
      ...c,
      subs:c.subcategories.map(s=>({...s,items:s.items.filter(i=>selectedDiet==='combo'||i.dietary===selectedDiet)})).filter(s=>s.items.some(Boolean))
    })).filter(c=>c.subs.length);
    if(!activeCategory || !visibleCats.some(c=>c.id===activeCategory)) activeCategory=visibleCats[0]?.id||null;
    categoryTabs.innerHTML=visibleCats.map(c=>`<button type="button" data-cat="${c.id}" class="${c.id===activeCategory?'active':''}">${escapeHtml(c.name)}</button>`).join('');
    categoryTabs.querySelectorAll('button').forEach(btn=>btn.addEventListener('click',()=>{ activeCategory=Number(btn.dataset.cat); render(); document.getElementById(`cat-${activeCategory}`)?.scrollIntoView({behavior:'smooth',block:'start'}); }));
    const draft=DraftStore.load();
    content.innerHTML=visibleCats.map(c=>`<section class="menu-section" id="cat-${c.id}">
      <div class="menu-section-title"><h2>${escapeHtml(c.name)}</h2><span class="muted">${c.subs.reduce((n,s)=>n+s.items.length,0)} choices</span></div>
      ${c.subs.map(s=>`<div><div class="subcategory-title">${escapeHtml(s.name)}</div><div class="menu-list">${s.items.map(i=>itemCard(i,draft.item_ids.includes(i.id))).join('')}</div></div>`).join('')}
    </section>`).join('') || '<div class="empty">No items match this selection.</div>';
    content.querySelectorAll('[data-add-item]').forEach(btn=>btn.addEventListener('click',()=>{ DraftStore.toggleItem(Number(btn.dataset.addItem)); render(); updateBasketBar(); }));
    updateBasketBar();
  }
  function itemCard(i,selected){return `<article class="menu-item ${selected?'selected':''} ${i.image_url?'has-image':''}">${i.image_url?`<img class="menu-item-image" src="${escapeHtml(i.image_url)}" alt="${escapeHtml(i.name)}" loading="lazy">`:''}<div><div class="menu-item-name">${escapeHtml(i.name)}</div>${i.description?`<div class="menu-item-desc">${escapeHtml(i.description)}</div>`:''}<div class="diet-dot ${i.dietary}">${i.dietary==='veg'?'Veg':'Non Veg'}</div></div><button type="button" class="add-btn ${selected?'active':''}" aria-label="${selected?'Remove':'Add'} ${escapeHtml(i.name)}" data-add-item="${i.id}">${selected?'✓':'+'}</button></article>`;}
  menuBtns.forEach(b=>b.addEventListener('click',()=>{selectedMenu=Number(b.dataset.menuChoice); activeCategory=null; render();}));
  dietBtns.forEach(b=>b.addEventListener('click',()=>{selectedDiet=b.dataset.dietChoice; activeCategory=null; render();}));
  updateRequestCount();
  render();
}

function updateBasketBar(){
  const el=document.querySelector('[data-basket-count]'); if(!el) return;
  const n=DraftStore.load().item_ids.length; el.textContent=formatCount(n);
}

function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}

function initReview(){
  const root=document.querySelector('[data-review-root]'); if(!root) return;
  const detailsBox=document.querySelector('[data-review-details]'); const itemsBox=document.querySelector('[data-review-items]'); const requestsBox=document.querySelector('[data-review-requests]'); const submit=document.querySelector('[data-submit-quote]');
  const notesInput=document.querySelector('[data-customer-notes]');
  const draft=DraftStore.load();
  if(!draft.details?.name){ location.replace('/order?next=/review'); return; }
  const d=draft.details;
  detailsBox.innerHTML=`<div class="order-meta"><div class="meta-row"><strong>Name</strong><span>${escapeHtml(d.name)}</span></div><div class="meta-row"><strong>Phone</strong><span>${escapeHtml(d.phone)}</span></div><div class="meta-row"><strong>WhatsApp</strong><span>${escapeHtml(d.whatsapp)}</span></div><div class="meta-row"><strong>Event</strong><span>${escapeHtml(d.event_name)}</span></div><div class="meta-row"><strong>Date</strong><span>${escapeHtml(d.event_date)}</span></div><div class="meta-row"><strong>Time</strong><span>${escapeHtml(d.event_time)}</span></div><div class="meta-row"><strong>Guests</strong><span>${escapeHtml(d.adults)} adults + ${escapeHtml(d.kids)} kids</span></div><div class="meta-row"><strong>Address</strong><span>${escapeHtml(d.address)}, ${escapeHtml(d.eircode)}</span></div></div>`;
  if(notesInput){ notesInput.value=draft.customer_notes||''; notesInput.addEventListener('input',()=>DraftStore.setCustomerNotes(notesInput.value)); }
  const renderRequests=(state)=>{
    const requests=state.requested_dishes||[];
    requestsBox.innerHTML=requests.length?`<div class="requested-dish-list">${requests.map(name=>`<div class="requested-dish-row"><strong>${escapeHtml(name)}</strong><span class="request-status pending">Needs confirmation</span></div>`).join('')}</div>`:'<div class="empty">No extra dishes requested.</div>';
  };
  const updateAvailability=(state)=>{ if(submit) submit.disabled=!((state.item_ids||[]).length||(state.requested_dishes||[]).length); };
  renderRequests(draft); updateAvailability(draft);
  renderReviewItems(draft.item_ids, itemsBox, submit, draft.requested_dishes.length);
  window.addEventListener('draftchange',e=>{ const state=e.detail||DraftStore.load(); renderRequests(state); updateAvailability(state); renderReviewItems(state.item_ids||[],itemsBox,submit,(state.requested_dishes||[]).length); });
  submit?.addEventListener('click',async()=>{
    const current=DraftStore.load(); if(!current.item_ids.length&&!current.requested_dishes.length) return;
    submit.disabled=true; const original=submit.textContent; submit.textContent='Sending quote…';
    const errorBox=document.querySelector('[data-submit-error]'); errorBox.hidden=true;
    try{
      const res=await fetch('/api/quotes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({details:current.details,item_ids:current.item_ids,requested_dishes:current.requested_dishes,customer_notes:current.customer_notes})});
      const body=await res.json();
      if(!res.ok||!body.ok){
        const errors=body.errors&&typeof body.errors==='object'?Object.values(body.errors):[];
        const message=errors.length?errors.join(' '):(body.error||'Could not send quote.');
        throw new Error(message);
      }
      localStorage.setItem('lastCateringOrderToken',body.token); DraftStore.clear(); location.href='/orders/'+body.token+'?submitted=1';
    }catch(err){
      errorBox.textContent=err.message||'Could not send quote. Try again.';
      errorBox.hidden=false;
      errorBox.insertAdjacentHTML('beforeend',' <a class="error-fix-link" href="/order?next=/review">Edit event details</a>');
      errorBox.scrollIntoView({behavior:'smooth',block:'center'});
      submit.disabled=false; submit.textContent=original;
    }
  });
}

async function renderReviewItems(ids,box,submit,requestedCount=0){
  if(!ids.length){ box.innerHTML='<div class="empty">No standard menu items selected. <a href="/menu"><strong>Choose menu items</strong></a></div>'; if(submit)submit.disabled=requestedCount===0; return; }
  try{
    const res=await fetch('/api/menu-items?ids='+encodeURIComponent(ids.join(','))); const items=await res.json();
    const groups={}; items.forEach(i=>{(((groups[i.menu]??={})[i.category]??={})[i.subcategory]??=[]).push(i)});
    box.innerHTML=Object.entries(groups).map(([m,cats])=>`<div class="review-group"><h3>${escapeHtml(m)}</h3>${Object.entries(cats).map(([c,subs])=>`<div class="review-category">${escapeHtml(c)}</div>${Object.entries(subs).map(([s,arr])=>`${s!=='Main Selection'?`<div class="help">${escapeHtml(s)}</div>`:''}${arr.map(i=>`<div class="review-item"><span>${escapeHtml(i.name)}</span><button type="button" data-remove="${i.id}">Remove</button></div>`).join('')}`).join('')}`).join('')}</div>`).join('');
    box.querySelectorAll('[data-remove]').forEach(b=>b.addEventListener('click',()=>DraftStore.removeItem(Number(b.dataset.remove)))); if(submit)submit.disabled=false;
  }catch{ box.innerHTML='<div class="notice error">Could not load your selected items. Return to the menu and try again.</div>'; if(submit)submit.disabled=true; }
}

function initDraftControls(){
  document.querySelectorAll('[data-clear-draft]').forEach(btn=>btn.addEventListener('click',()=>{ if(confirm('Clear your saved catering draft?')){DraftStore.clear(); location.href='/';} }));
  const recent=document.querySelector('[data-recent-order]'); if(recent){const t=localStorage.getItem('lastCateringOrderToken'); if(t){recent.href='/orders/'+t; recent.hidden=false;}}
}

document.addEventListener('DOMContentLoaded',()=>{initDetailsForm();initMenu();initReview();initDraftControls();updateBasketBar();});
