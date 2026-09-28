const DraftStore = (() => {
  const KEY = 'cateringDraftV1';
  const blank = () => ({details:{}, item_ids:[], requested_dishes:[], customer_notes:'', last_updated:null});
  const load = () => { try { const d=JSON.parse(localStorage.getItem(KEY))||blank(); d.details=d.details||{}; d.item_ids=Array.isArray(d.item_ids)?d.item_ids:[]; d.requested_dishes=Array.isArray(d.requested_dishes)?d.requested_dishes:[]; d.customer_notes=String(d.customer_notes||''); return d; } catch { return blank(); } };
  const save = (draft) => { draft.last_updated=new Date().toISOString(); localStorage.setItem(KEY,JSON.stringify(draft)); window.dispatchEvent(new CustomEvent('draftchange',{detail:draft})); };
  const clear = () => { localStorage.removeItem(KEY); window.dispatchEvent(new CustomEvent('draftchange',{detail:blank()})); };
  const setDetails = (details) => { const d=load(); d.details=details; save(d); return d; };
  const toggleItem = (id) => { const d=load(); const n=Number(id); d.item_ids=d.item_ids.includes(n)?d.item_ids.filter(x=>x!==n):[...d.item_ids,n]; save(d); return d; };
  const removeItem = (id) => { const d=load(); d.item_ids=d.item_ids.filter(x=>x!==Number(id)); save(d); return d; };
  const setRequestedDishes = (dishes) => { const d=load(); d.requested_dishes=dishes; save(d); return d; };
  const setCustomerNotes = (notes) => { const d=load(); d.customer_notes=String(notes||''); save(d); return d; };
  return {load,save,clear,setDetails,toggleItem,removeItem,setRequestedDishes,setCustomerNotes};
})();
window.DraftStore=DraftStore;

function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function formatCount(n){return `${n} item${n===1?'':'s'} selected`;}
function safeHeadingColor(v){const s=String(v||'').trim();return /^#[0-9a-f]{6}$/i.test(s)?s:'#94A3B8';}
function formatMenuPrice(v){const n=Number(v);return Number.isFinite(n)?`€${n.toFixed(2)}`:'';}
function dayFromDate(value){if(!value)return '';const d=new Date(value+'T12:00:00');return Number.isFinite(d.getTime())?d.toLocaleDateString('en-IE',{weekday:'long'}):'';}

function initDetailsForm(){
  const form=document.querySelector('[data-details-form]'); if(!form) return;
  const draft=DraftStore.load();
  Object.entries(draft.details||{}).forEach(([k,v])=>{const el=form.elements[k]; if(el&&el.type!=='submit') el.value=v??'';});
  const same=document.getElementById('same-whatsapp'), phone=form.elements.phone, wa=form.elements.whatsapp;
  const dateInput=form.elements.event_date, dayInput=form.elements.event_day, eircode=form.elements.eircode, errorBox=document.querySelector('[data-details-error]');
  const earliestEventDate=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+3);return d;};
  const toDateInput=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  if(dateInput) dateInput.min=toDateInput(earliestEventDate());
  const syncDay=()=>{if(dayInput)dayInput.value=dayFromDate(dateInput?.value||'');}; syncDay(); dateInput?.addEventListener('change',syncDay);
  document.querySelectorAll('[data-native-picker]').forEach(input=>input.addEventListener('click',()=>{if(typeof input.showPicker==='function'){try{input.showPicker();}catch{}}}));
  const digitsOnly=el=>{if(!el)return;el.value=String(el.value||'').replace(/\D/g,'').slice(0,10);};
  phone?.addEventListener('input',()=>{digitsOnly(phone);if(same?.checked){wa.value=phone.value;}});
  wa?.addEventListener('input',()=>digitsOnly(wa));
  eircode?.addEventListener('input',()=>{eircode.value=String(eircode.value||'').replace(/[^a-z0-9]/gi,'').toUpperCase().slice(0,7);});
  digitsOnly(phone);digitsOnly(wa);if(eircode)eircode.value=String(eircode.value||'').replace(/[^a-z0-9]/gi,'').toUpperCase().slice(0,7);
  if(phone&&wa&&phone.value&&phone.value===wa.value) same.checked=true;
  same?.addEventListener('change',()=>{if(same.checked) wa.value=phone.value;});
  const fail=(message,field)=>{if(errorBox){errorBox.textContent=message;errorBox.hidden=false;}else alert(message); form.elements[field]?.focus();};
  form.addEventListener('submit',e=>{
    e.preventDefault(); if(errorBox) errorBox.hidden=true; if(!form.reportValidity()) return;
    const fd=new FormData(form), details={};
    ['name','phone','whatsapp','email','event_date','event_day','event_name','event_time','delivery_time','adults','kids','address','eircode'].forEach(k=>details[k]=String(fd.get(k)||'').trim());
    if(!/^[0-9]{7,10}$/.test(details.phone)){fail('Phone number must contain digits only and be no more than 10 digits.','phone');return;}
    if(!/^[0-9]{7,10}$/.test(details.whatsapp)){fail('WhatsApp number must contain digits only and be no more than 10 digits.','whatsapp');return;}
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(details.email)){fail('Enter a valid email address for your catering quote.','email');return;}
    details.eircode=details.eircode.replace(/\s/g,'').toUpperCase();
    if(!/^[A-Z0-9]{7}$/.test(details.eircode)){fail('Eircode must be exactly 7 letters and numbers.','eircode');return;}
    details.event_day=dayFromDate(details.event_date);
    if((Number(details.adults)||0)+(Number(details.kids)||0)<1){fail('Enter at least one guest in Adults or Kids.','adults');return;}
    const selectedDate=new Date(`${details.event_date}T12:00:00`);
    if(!Number.isFinite(selectedDate.getTime())||selectedDate.getTime()<earliestEventDate().getTime()){fail('Please choose the earliest available date shown or a later date. We require two full days notice.','event_date');return;}
    DraftStore.setDetails(details); location.href=form.dataset.next||'/menu';
  });
}

function initMenu(){
  const root=document.querySelector('[data-menu-root]'); if(!root) return;
  const data=JSON.parse(document.getElementById('menu-data').textContent||'[]');
  const regionBtns=[...document.querySelectorAll('[data-menu-choice]')];
  const dietBtns=[...document.querySelectorAll('[data-diet-choice]')];
  const categoryTabs=document.querySelector('[data-category-tabs]'), content=document.querySelector('[data-menu-content]');
  const filterDialog=document.querySelector('[data-menu-filter-dialog]'), requestDialog=document.querySelector('[data-request-dialog]');
  const requestInput=document.querySelector('[data-request-input]'), requestCount=document.querySelector('[data-request-count]');
  const comboDialog=document.querySelector('[data-combo-dialog]'), comboList=document.querySelector('[data-combo-list]'), comboTitle=document.querySelector('[data-combo-title]');
  let selectedMenu=null;
  let selectedDiet='veg';
  let activeCategory=null;
  let searchTerm='';
  let categoryObserver=null;
  const itemMap=new Map();
  data.forEach(m=>m.categories.forEach(c=>c.subcategories.forEach(sub=>sub.items.forEach(i=>{if(!itemMap.has(i.id))itemMap.set(i.id,{...i,menu:m.name,category:c.name,subcategory:sub.name});}))));
  window.__menuItemMap=itemMap;

  const updateRequestCount=()=>{const n=DraftStore.load().requested_dishes.length;if(requestCount)requestCount.textContent=n?`(${n})`:'';};
  document.querySelector('[data-open-request-dialog]')?.addEventListener('click',()=>{const d=DraftStore.load();requestInput.value=d.requested_dishes.join('\n');requestDialog?.showModal();});
  document.querySelector('[data-save-requests]')?.addEventListener('click',()=>{
    const lines=String(requestInput?.value||'').split(/\r?\n/).map(x=>x.replace(/\s+/g,' ').trim()).filter(Boolean), unique=[], seen=new Set();
    for(const line of lines){const key=line.toLowerCase();if(!seen.has(key)){seen.add(key);unique.push(line.slice(0,180));}}
    if(unique.length>20){alert('Please request no more than 20 dishes.');return;}
    DraftStore.setRequestedDishes(unique);updateRequestCount();requestDialog?.close();
  });
  requestDialog?.addEventListener('click',e=>{if(e.target===requestDialog)requestDialog.close();});
  document.querySelector('[data-open-menu-filter]')?.addEventListener('click',()=>filterDialog?.showModal());
  filterDialog?.addEventListener('click',e=>{if(e.target===filterDialog)filterDialog.close();});
  document.querySelectorAll('[data-close-combo]').forEach(btn=>btn.addEventListener('click',()=>comboDialog?.close()));
  comboDialog?.addEventListener('click',e=>{if(e.target===comboDialog)comboDialog.close();});

  function visibleMenus(){return selectedMenu===null?data:data.filter(m=>m.id===selectedMenu);}
  function buildCategories(){
    const categories=new Map();
    visibleMenus().forEach(menu=>menu.categories.forEach(category=>{
      let cat=categories.get(category.name);
      if(!cat){cat={id:`cat-${categories.size}`,name:category.name,subs:new Map()};categories.set(category.name,cat);}
      category.subcategories.forEach(sub=>{
        let targetSub=cat.subs.get(sub.name);
        if(!targetSub){targetSub={id:sub.id,name:sub.name,items:new Map(),sort_order:sub.sort_order,heading_color:sub.heading_color||'#94A3B8'};cat.subs.set(sub.name,targetSub);}
        sub.items.forEach(item=>{
          const matchesDiet=selectedDiet==='combo'||item.dietary===selectedDiet||item.dietary==='both';
          const haystack=(item.name+' '+(item.description||'')+' '+category.name+' '+sub.name).toLowerCase();
          const matchesSearch=!searchTerm||haystack.includes(searchTerm);
          if(!matchesDiet||!matchesSearch)return;
          if(!targetSub.items.has(item.id)){targetSub.items.set(item.id,{...item,menu:menu.name});if(item.heading_color)targetSub.heading_color=item.heading_color;}
        });
      });
    }));
    return [...categories.values()].map(cat=>({
      id:cat.id,name:cat.name,
      subs:[...cat.subs.values()].map(sub=>({...sub,items:[...sub.items.values()]})).filter(sub=>sub.items.length)
    })).filter(cat=>cat.subs.length);
  }

  async function showComboSuggestions(itemId){
    try{
      const res=await fetch('/api/menu-combinations?item_id='+encodeURIComponent(itemId));
      if(!res.ok)return;
      const body=await res.json();
      const selected=new Set(DraftStore.load().item_ids||[]);
      const items=(body.items||[]).filter(item=>!selected.has(Number(item.id)));
      if(!items.length)return;
      comboTitle.textContent=body.title||'Goes Well With This';
      comboList.innerHTML=items.map(item=>{
        const label=item.dietary==='veg'?'Veg':item.dietary==='nonveg'?'Non Veg':'Both';
        return `<article class="combo-suggestion-card ${escapeHtml(item.dietary)}">${item.image_url?`<img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}" loading="lazy">`:''}<div class="combo-suggestion-copy"><strong>${escapeHtml(item.name)}</strong>${item.description?`<span>${escapeHtml(item.description)}</span>`:''}${item.price!=null?`<span class="combo-price">${formatMenuPrice(item.price)}</span>`:''}<span class="diet-dot ${escapeHtml(item.dietary)}">${label}</span></div><button type="button" class="btn small combo-add" data-combo-add="${item.id}">Add</button></article>`;
      }).join('');
      comboList.querySelectorAll('[data-combo-add]').forEach(btn=>btn.addEventListener('click',()=>{
        const id=Number(btn.dataset.comboAdd);const state=DraftStore.load();
        if(!state.item_ids.includes(id))DraftStore.toggleItem(id);
        btn.textContent='Added ✓';btn.disabled=true;render();updateBasketBar();
      }));
      comboDialog?.showModal();
    }catch{}
  }

  function render(){
    regionBtns.forEach(b=>b.classList.toggle('active',b.dataset.menuChoice==='all'?selectedMenu===null:Number(b.dataset.menuChoice)===selectedMenu));
    dietBtns.forEach(b=>b.classList.toggle('active',b.dataset.dietChoice===selectedDiet));
    const cats=buildCategories();
    if(!activeCategory||!cats.some(c=>c.id===activeCategory))activeCategory=cats[0]?.id||null;
    categoryTabs.innerHTML=cats.map(c=>`<button type="button" data-cat="${c.id}" class="${c.id===activeCategory?'active':''}" aria-pressed="${c.id===activeCategory?'true':'false'}">${escapeHtml(c.name)}</button>`).join('');
    categoryTabs.querySelectorAll('button').forEach(btn=>btn.addEventListener('click',()=>{activeCategory=btn.dataset.cat;categoryTabs.querySelectorAll('button').forEach(x=>{const on=x.dataset.cat===activeCategory;x.classList.toggle('active',on);x.setAttribute('aria-pressed',String(on));});document.getElementById(activeCategory)?.scrollIntoView({behavior:'smooth',block:'start'});}));
    const draft=DraftStore.load();
    content.innerHTML=cats.map(c=>`<section class="menu-section" id="${c.id}"><div class="menu-section-title"><h2>${escapeHtml(c.name)}</h2><span class="muted">${c.subs.reduce((n,sub)=>n+sub.items.length,0)} choices</span></div>${c.subs.map(sub=>`<div class="menu-subsection"><div class="subcategory-title" style="--heading-color:${safeHeadingColor(sub.heading_color)}">${escapeHtml(sub.name)}</div><div class="menu-list">${sub.items.map(i=>itemCard(i,draft.item_ids.includes(i.id))).join('')}</div></div>`).join('')}</section>`).join('')||'<div class="empty">No items match these filters.</div>';
    if(categoryObserver)categoryObserver.disconnect();
    if('IntersectionObserver' in window){categoryObserver=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];if(!visible)return;activeCategory=visible.target.id;categoryTabs.querySelectorAll('button').forEach(x=>{const on=x.dataset.cat===activeCategory;x.classList.toggle('active',on);x.setAttribute('aria-pressed',String(on));if(on)x.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});});},{rootMargin:'-145px 0px -62% 0px',threshold:[0,.01]});content.querySelectorAll('.menu-section').forEach(section=>categoryObserver.observe(section));}
    content.querySelectorAll('[data-add-item]').forEach(btn=>btn.addEventListener('click',()=>{
      const id=Number(btn.dataset.addItem);const wasSelected=DraftStore.load().item_ids.includes(id);DraftStore.toggleItem(id);render();updateBasketBar();if(!wasSelected)showComboSuggestions(id);
    }));
    updateBasketBar();
  }
  function itemCard(i,selected){const label=i.dietary==='veg'?'Veg':i.dietary==='nonveg'?'Non Veg':'Both';return `<article class="menu-item ${selected?'selected':''} ${i.image_url?'has-image':''} dietary-card-${escapeHtml(i.dietary)}">${i.image_url?`<img class="menu-item-image" src="${escapeHtml(i.image_url)}" alt="${escapeHtml(i.name)}" loading="lazy">`:''}<div class="menu-item-copy"><div class="menu-item-name">${escapeHtml(i.name)}</div>${i.price!=null?`<div class="menu-item-price">${formatMenuPrice(i.price)}</div>`:''}${i.description?`<div class="menu-item-desc">${escapeHtml(i.description)}</div>`:''}<div class="diet-dot ${escapeHtml(i.dietary)}">${label}</div></div><button type="button" class="add-btn ${selected?'active':''}" aria-label="${selected?'Remove':'Add'} ${escapeHtml(i.name)}" data-add-item="${i.id}">${selected?'✓':'+'}</button></article>`;}
  regionBtns.forEach(b=>b.addEventListener('click',()=>{selectedMenu=b.dataset.menuChoice==='all'?null:Number(b.dataset.menuChoice);activeCategory=null;render();}));
  dietBtns.forEach(b=>b.addEventListener('click',()=>{selectedDiet=b.dataset.dietChoice;activeCategory=null;render();if(b.closest('[data-menu-filter-dialog]'))filterDialog?.close();}));
  const searchInput=document.querySelector('[data-menu-search]');
  searchInput?.addEventListener('input',()=>{searchTerm=String(searchInput.value||'').trim().toLowerCase();activeCategory=null;render();});
  updateRequestCount();render();
}

function updateBasketBar(){const el=document.querySelector('[data-basket-count]');if(el)el.textContent=formatCount(DraftStore.load().item_ids.length);}

function initReview(){
  const root=document.querySelector('[data-review-root]');if(!root)return;
  const detailsBox=document.querySelector('[data-review-details]'),itemsBox=document.querySelector('[data-review-items]'),requestsBox=document.querySelector('[data-review-requests]'),submit=document.querySelector('[data-submit-quote]'),notesInput=document.querySelector('[data-customer-notes]');
  const draft=DraftStore.load();if(!draft.details?.name){location.replace('/order?next=/review');return;}const d=draft.details;
  detailsBox.innerHTML=`<div class="order-meta"><div class="meta-row"><strong>Name</strong><span>${escapeHtml(d.name)}</span></div><div class="meta-row"><strong>Phone</strong><span>${escapeHtml(d.phone)}</span></div><div class="meta-row"><strong>WhatsApp</strong><span>${escapeHtml(d.whatsapp)}</span></div><div class="meta-row"><strong>Email</strong><span>${escapeHtml(d.email)}</span></div><div class="meta-row"><strong>Event</strong><span>${escapeHtml(d.event_name)}</span></div><div class="meta-row"><strong>Date</strong><span>${escapeHtml(d.event_date)}</span></div><div class="meta-row"><strong>Day</strong><span>${escapeHtml(d.event_day||dayFromDate(d.event_date))}</span></div><div class="meta-row"><strong>Event Time</strong><span>${escapeHtml(d.event_time)}</span></div><div class="meta-row"><strong>Delivery Time</strong><span>${escapeHtml(d.delivery_time)}</span></div><div class="meta-row"><strong>Guests</strong><span>${escapeHtml(d.adults)} adults + ${escapeHtml(d.kids)} kids</span></div><div class="meta-row"><strong>Address</strong><span>${escapeHtml(d.address)}, ${escapeHtml(d.eircode)}</span></div></div>`;
  if(notesInput){notesInput.value=draft.customer_notes||'';notesInput.addEventListener('input',()=>DraftStore.setCustomerNotes(notesInput.value));}
  const renderRequests=state=>{const requests=state.requested_dishes||[];requestsBox.innerHTML=requests.length?`<div class="requested-dish-list">${requests.map(name=>`<div class="requested-dish-row"><strong>${escapeHtml(name)}</strong><span class="request-status pending">Needs Confirmation</span></div>`).join('')}</div>`:'<div class="empty">No dishes requested.</div>';};
  const updateAvailability=state=>{if(submit)submit.disabled=!((state.item_ids||[]).length||(state.requested_dishes||[]).length);};
  renderRequests(draft);updateAvailability(draft);renderReviewItems(draft.item_ids,itemsBox,submit,draft.requested_dishes.length);
  window.addEventListener('draftchange',e=>{const state=e.detail||DraftStore.load();renderRequests(state);updateAvailability(state);renderReviewItems(state.item_ids||[],itemsBox,submit,(state.requested_dishes||[]).length);});
  submit?.addEventListener('click',async()=>{
    const current=DraftStore.load();if(!current.item_ids.length&&!current.requested_dishes.length)return;submit.disabled=true;const original=submit.textContent;submit.textContent='Sending Quote…';const errorBox=document.querySelector('[data-submit-error]');errorBox.hidden=true;
    try{const editToken=localStorage.getItem('cateringEditOrderToken');const endpoint=editToken?'/api/orders/'+encodeURIComponent(editToken)+'/menu-update':'/api/quotes';const res=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({details:current.details,item_ids:current.item_ids,requested_dishes:current.requested_dishes,customer_notes:current.customer_notes})});const body=await res.json();if(!res.ok||!body.ok){const errors=body.errors&&typeof body.errors==='object'?Object.values(body.errors):[];throw new Error(errors.length?errors.join(' '):(body.error||'Could not send quote.'));}localStorage.setItem('lastCateringOrderToken',body.token);localStorage.removeItem('cateringEditOrderToken');DraftStore.clear();location.href='/orders/'+body.token+(editToken?'?updated=1':'?submitted=1');}
    catch(err){errorBox.textContent=err.message||'Could not send quote. Try again.';errorBox.hidden=false;errorBox.insertAdjacentHTML('beforeend',' <a class="error-fix-link" href="/order?next=/review">Edit Event Details</a>');errorBox.scrollIntoView({behavior:'smooth',block:'center'});submit.disabled=false;submit.textContent=original;}
  });
}

async function renderReviewItems(ids,box,submit,requestedCount=0){
  if(!ids.length){box.innerHTML='<div class="empty">No standard menu items selected. <a href="/menu"><strong>Choose Menu Items</strong></a></div>';if(submit)submit.disabled=requestedCount===0;return;}
  try{const res=await fetch('/api/menu-items?ids='+encodeURIComponent(ids.join(','))),items=await res.json(),groups={};items.forEach(i=>{(((groups[i.menu]??={})[i.category]??={})[i.subcategory]??=[]).push(i)});
    box.innerHTML=Object.entries(groups).map(([m,cats])=>`<div class="review-group"><h3>${escapeHtml(m)}</h3>${Object.entries(cats).map(([c,subs])=>{let counter=1;return `<div class="review-category review-category-highlight">${escapeHtml(c)}</div>${Object.entries(subs).map(([s,arr])=>`${s!=='Main Selection'?`<div class="help">${escapeHtml(s)}</div>`:''}<ol class="review-numbered-list" start="${counter}">${arr.map(i=>`<li class="dietary-list-item ${escapeHtml(i.dietary)}"><span>${escapeHtml(i.name)}${i.price!=null?` <strong class="review-item-price">${formatMenuPrice(i.price)}</strong>`:''}</span><button type="button" data-remove="${i.id}">Remove</button></li>`).join('')}</ol>${(()=>{counter+=arr.length;return ''})()}`).join('')}`}).join('')}</div>`).join('');
    box.querySelectorAll('[data-remove]').forEach(b=>b.addEventListener('click',()=>DraftStore.removeItem(Number(b.dataset.remove))));if(submit)submit.disabled=false;
  }catch{box.innerHTML='<div class="notice error">Could not load your selected items. Return to the menu and try again.</div>';if(submit)submit.disabled=true;}
}

function initDraftControls(){document.querySelectorAll('[data-clear-draft]').forEach(btn=>btn.addEventListener('click',()=>{if(confirm('Clear your saved catering draft?')){DraftStore.clear();location.href='/';}}));const recent=document.querySelector('[data-recent-order]');if(recent){const t=localStorage.getItem('lastCateringOrderToken');if(t){recent.href='/orders/'+t;recent.hidden=false;}}}
document.addEventListener('DOMContentLoaded',()=>{initDetailsForm();initMenu();initReview();initDraftControls();updateBasketBar();});
