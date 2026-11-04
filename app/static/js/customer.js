const DraftStore = (() => {
  const KEY = 'cateringDraftV1';
  const blank = () => ({details:{}, item_ids:[], item_comments:{}, item_variants:{}, requested_dishes:[], customer_notes:'', last_updated:null});
  const load = () => { try { const d=JSON.parse(localStorage.getItem(KEY))||blank(); d.details=d.details||{}; d.item_ids=Array.isArray(d.item_ids)?d.item_ids:[]; d.item_comments=(d.item_comments&&typeof d.item_comments==='object'&&!Array.isArray(d.item_comments))?d.item_comments:{}; d.item_variants=(d.item_variants&&typeof d.item_variants==='object'&&!Array.isArray(d.item_variants))?d.item_variants:{}; d.requested_dishes=Array.isArray(d.requested_dishes)?d.requested_dishes:[]; d.customer_notes=String(d.customer_notes||''); return d; } catch { return blank(); } };
  const save = (draft) => { draft.last_updated=new Date().toISOString(); localStorage.setItem(KEY,JSON.stringify(draft)); window.dispatchEvent(new CustomEvent('draftchange',{detail:draft})); };
  const clear = () => { localStorage.removeItem(KEY); window.dispatchEvent(new CustomEvent('draftchange',{detail:blank()})); };
  const setDetails = (details) => { const d=load(); d.details=details; save(d); return d; };
  const toggleItem = (id) => { const d=load(); const n=Number(id); if(d.item_ids.includes(n)){d.item_ids=d.item_ids.filter(x=>x!==n);delete d.item_comments[String(n)];delete d.item_variants[String(n)];}else{d.item_ids=[...d.item_ids,n];} save(d); return d; };
  const removeItem = (id) => { const d=load(); const n=Number(id); d.item_ids=d.item_ids.filter(x=>x!==n);delete d.item_comments[String(n)];delete d.item_variants[String(n)];save(d);return d; };
  const setItemComment = (id,comment) => { const d=load(); const n=Number(id),key=String(n),value=String(comment||'').replace(/\s+/g,' ').trim().slice(0,300);if(value)d.item_comments[key]=value;else delete d.item_comments[key];save(d);return d; };
  const setItemVariant = (id,variant) => { const d=load(); const n=Number(id),key=String(n),value=String(variant||'').trim();if(value)d.item_variants[key]=value;else delete d.item_variants[key];if(value&&!d.item_ids.includes(n))d.item_ids=[...d.item_ids,n];save(d);return d; };
  const setRequestedDishes = (dishes) => { const d=load(); d.requested_dishes=dishes; save(d); return d; };
  const setCustomerNotes = (notes) => { const d=load(); d.customer_notes=String(notes||''); save(d); return d; };
  return {load,save,clear,setDetails,toggleItem,removeItem,setItemComment,setItemVariant,setRequestedDishes,setCustomerNotes};
})();
window.DraftStore=DraftStore;

function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function formatCount(n){return `${n} item${n===1?'':'s'} selected`;}
function safeHeadingColor(v){const s=String(v||'').trim();return /^#[0-9a-f]{6}$/i.test(s)?s:'#94A3B8';}
function formatMenuPrice(v){const n=Number(v);return Number.isFinite(n)?`€${n.toFixed(2)}`:'';}
function dayFromDate(value){if(!value)return '';const d=new Date(value+'T12:00:00');return Number.isFinite(d.getTime())?d.toLocaleDateString('en-IE',{weekday:'long'}):'';}

function quarterHourLabel(value){
  const m=/^(\d{1,2}):(\d{2})$/.exec(String(value||''));
  if(!m)return '';
  const hour24=Number(m[1]), minute=Number(m[2]);
  if(hour24<0||hour24>23||minute<0||minute>59)return '';
  const suffix=hour24>=12?'PM':'AM';
  const hour12=hour24%12||12;
  return `${hour12}:${String(minute).padStart(2,'0')} ${suffix}`;
}
function snapToQuarterHour(value){
  const m=/^(\d{1,2}):(\d{2})/.exec(String(value||''));
  if(!m)return '';
  let total=Number(m[1])*60+Number(m[2]);
  if(!Number.isFinite(total))return '';
  total=(Math.round(total/15)*15)%(24*60);
  const h=Math.floor(total/60),min=total%60;
  return `${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}`;
}
function initQuarterHourTimePickers(form){
  const dialog=document.querySelector('[data-quarter-time-dialog]');
  const optionRoot=dialog?.querySelector('[data-quarter-time-options]');
  const title=dialog?.querySelector('[data-quarter-time-title]');
  if(!dialog||!optionRoot)return {sync:()=>{}};
  let activeInput=null,activeTrigger=null;
  const options=[];
  for(let minutes=0;minutes<24*60;minutes+=15){
    const h=Math.floor(minutes/60),m=minutes%60;
    const value=`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;
    options.push(`<button type="button" class="quarter-time-option" data-time-option="${value}">${quarterHourLabel(value)}</button>`);
  }
  optionRoot.innerHTML=options.join('');
  const sync=()=>{
    form.querySelectorAll('[data-time-trigger]').forEach(trigger=>{
      const input=form.elements[trigger.dataset.timeTarget];
      if(!input)return;
      if(input.value)input.value=snapToQuarterHour(input.value);
      const label=trigger.querySelector('[data-time-label]');
      const text=quarterHourLabel(input.value);
      if(label)label.textContent=text||trigger.dataset.timeTitle||'Choose Time';
      trigger.classList.toggle('has-value',Boolean(text));
    });
  };
  form.querySelectorAll('[data-time-trigger]').forEach(trigger=>trigger.addEventListener('click',()=>{
    activeTrigger=trigger;
    activeInput=form.elements[trigger.dataset.timeTarget];
    if(title)title.textContent=trigger.dataset.timeTitle||'Choose Time';
    optionRoot.querySelectorAll('[data-time-option]').forEach(btn=>btn.classList.toggle('selected',btn.dataset.timeOption===activeInput?.value));
    if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
    requestAnimationFrame(()=>{
      const selected=optionRoot.querySelector('.quarter-time-option.selected');
      (selected||optionRoot.querySelector('[data-time-option="12:00"]')||optionRoot.firstElementChild)?.scrollIntoView({block:'center'});
    });
  }));
  optionRoot.addEventListener('click',e=>{
    const btn=e.target.closest('[data-time-option]');
    if(!btn||!activeInput)return;
    activeInput.value=btn.dataset.timeOption;
    activeInput.dispatchEvent(new Event('input',{bubbles:true}));
    activeInput.dispatchEvent(new Event('change',{bubbles:true}));
    const label=activeTrigger?.querySelector('[data-time-label]');
    if(label)label.textContent=quarterHourLabel(activeInput.value);
    activeTrigger?.classList.add('has-value');
    if(dialog.open)dialog.close();else dialog.removeAttribute('open');
    activeTrigger?.focus();
  });
  dialog.querySelector('[data-quarter-time-close]')?.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});
  return {sync};
}


async function submitCurrentDraft(button,errorBox){
  const current=DraftStore.load();
  if(!current.item_ids.length&&!current.requested_dishes.length)throw new Error('Please choose at least one menu item or requested dish.');
  const editToken=localStorage.getItem('cateringEditOrderToken');
  const endpoint=editToken?'/api/orders/'+encodeURIComponent(editToken)+'/menu-update':'/api/quotes';
  const res=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({details:current.details,item_ids:current.item_ids,item_comments:current.item_comments,item_variants:current.item_variants,requested_dishes:current.requested_dishes,customer_notes:current.customer_notes})});
  const raw=await res.text();let body={};
  try{body=raw?JSON.parse(raw):{};}catch{body={ok:false,error:'We could not send your quote request. Please try again.'};}
  if(!res.ok||!body.ok){const errors=body.errors&&typeof body.errors==='object'?Object.values(body.errors):[];throw new Error(errors.length?errors.join(' '):(body.error||'Could not send quote.'));}
  localStorage.setItem('lastCateringOrderToken',body.token);localStorage.removeItem('cateringEditOrderToken');DraftStore.clear();
  location.href='/orders/'+body.token+(editToken?'?updated=1':'?submitted=1');
}

function initDetailsForm(){
  const form=document.querySelector('[data-details-form]'); if(!form) return;
  const timePickers=initQuarterHourTimePickers(form);
  const draft=DraftStore.load();
  Object.entries(draft.details||{}).forEach(([k,v])=>{const el=form.elements[k]; if(el&&el.type!=='submit') el.value=v??'';});
  timePickers.sync();
  const same=document.getElementById('same-whatsapp'), phone=form.elements.phone, wa=form.elements.whatsapp;
  const dateInput=form.elements.event_date, dayInput=form.elements.event_day, eircode=form.elements.eircode, errorBox=document.querySelector('[data-details-error]');
  const earliestEventDate=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+1);return d;};
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
  const fail=(message,field)=>{if(errorBox){errorBox.textContent=message;errorBox.hidden=false;}else alert(message); const target=form.elements[field];if(target?.type==='hidden'){form.querySelector(`[data-time-target="${field}"]`)?.focus();}else target?.focus();};
  const clearFieldError=el=>{const field=el?.closest('.field');if(!field)return;field.classList.remove('field-invalid');field.querySelector('[data-field-error]')?.remove();};
  const showFieldError=el=>{const field=el?.closest('.field');if(!field)return;field.classList.add('field-invalid');let msg=field.querySelector('[data-field-error]');if(!msg){msg=document.createElement('div');msg.dataset.fieldError='';msg.className='field-error-message';field.appendChild(msg);}msg.textContent=el.validationMessage||'This field is required.';};
  [...form.querySelectorAll('input[required],textarea[required],select[required]')].forEach(el=>{el.addEventListener('input',()=>clearFieldError(el));el.addEventListener('change',()=>clearFieldError(el));});
  form.addEventListener('submit',e=>{
    e.preventDefault(); if(errorBox) errorBox.hidden=true;
    const required=[...form.querySelectorAll('input[required],textarea[required],select[required]')];
    required.forEach(clearFieldError);
    const invalid=required.filter(el=>!el.checkValidity());
    if(invalid.length){invalid.forEach(showFieldError);invalid[0].closest('.field')?.scrollIntoView({behavior:'smooth',block:'center'});invalid[0].focus({preventScroll:true});return;}
    const fd=new FormData(form), details={};
    ['name','phone','whatsapp','email','event_date','event_day','event_name','event_time','delivery_time','adults','kids','address','eircode'].forEach(k=>details[k]=String(fd.get(k)||'').trim());
    if(!details.event_time){fail('Choose the event time.','event_time');return;}
    if(!details.delivery_time){fail('Choose the delivery time.','delivery_time');return;}
    if(!/^[0-9]{7,10}$/.test(details.phone)){fail('Phone number must contain digits only and be no more than 10 digits.','phone');return;}
    if(!/^[0-9]{7,10}$/.test(details.whatsapp)){fail('WhatsApp number must contain digits only and be no more than 10 digits.','whatsapp');return;}
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(details.email)){fail('Enter a valid email address for your catering quote.','email');return;}
    details.eircode=details.eircode.replace(/\s/g,'').toUpperCase();
    if(!/^[A-Z0-9]{7}$/.test(details.eircode)){fail('Eircode must be exactly 7 letters and numbers.','eircode');return;}
    details.event_day=dayFromDate(details.event_date);
    if((Number(details.adults)||0)+(Number(details.kids)||0)<1){fail('Enter at least one guest in Adults or Kids.','adults');return;}
    const selectedDate=new Date(`${details.event_date}T12:00:00`);
    if(!Number.isFinite(selectedDate.getTime())||selectedDate.getTime()<earliestEventDate().getTime()){fail('Please choose the earliest available date shown or a later date. Next-day catering requests are allowed.','event_date');return;}
    DraftStore.setDetails(details);
    if(form.dataset.finalSubmit==='true'){const submit=form.querySelector('button[type=submit]'),original=submit?.textContent;if(submit){submit.disabled=true;submit.textContent='Sending Quote…';}submitCurrentDraft(submit,errorBox).catch(err=>{if(errorBox){errorBox.textContent=err.message||'Could not send quote.';errorBox.hidden=false;errorBox.scrollIntoView({behavior:'smooth',block:'center'});}if(submit){submit.disabled=false;submit.textContent=original||'Send Quote Request';}});return;}
    location.href=form.dataset.next||'/menu';
  });
}

function initMenu(){
  const root=document.querySelector('[data-menu-root]'); if(!root) return;
  const data=JSON.parse(document.getElementById('menu-data').textContent||'[]');
  const regionBtns=[...document.querySelectorAll('[data-menu-choice]')];
  const dietBtns=[...document.querySelectorAll('[data-diet-choice]')];
  const categoryTabs=document.querySelector('[data-category-tabs]'), content=document.querySelector('[data-menu-content]');
  const filterDialog=document.querySelector('[data-menu-filter-dialog]'), requestDialog=document.querySelector('[data-request-dialog]');
  const categoryDialog=document.querySelector('[data-category-dialog]'), currentCategoryLabel=document.querySelector('[data-current-category]');
  const requestRows=document.querySelector('[data-request-rows]'), requestCount=document.querySelector('[data-request-count]');
  const comboDialog=document.querySelector('[data-combo-dialog]'), comboList=document.querySelector('[data-combo-list]'), comboTitle=document.querySelector('[data-combo-title]');
  const biryaniDialog=document.querySelector('[data-biryani-style-dialog]'), biryaniTitle=biryaniDialog?.querySelector('[data-biryani-style-title]');
  let pendingBiryaniItem=null;
  let selectedMenu=null;
  let selectedDiet='veg';
  let activeCategory=null;
  let searchTerm='';
  let searchMode=false;
  let categoryScrollHandler=null;
  let categoryScrollRaf=0;
  let categoryLockUntil=0;
  const itemMap=new Map();
  data.forEach(m=>m.categories.forEach(c=>c.subcategories.forEach(sub=>sub.items.forEach(i=>{if(!itemMap.has(i.id))itemMap.set(i.id,{...i,menu:m.name,category:c.name,subcategory:sub.name});}))));
  window.__menuItemMap=itemMap;

  const updateRequestCount=()=>{const n=DraftStore.load().requested_dishes.length;if(requestCount){requestCount.textContent=n?String(n):'';requestCount.hidden=n===0;}};
  const requestRowHtml=(value='',index=0)=>`<div class="requested-dish-row" data-request-row><div class="requested-dish-number">${index+1}</div><input type="text" maxlength="180" value="${escapeHtml(value)}" placeholder="Dish name" aria-label="Requested dish ${index+1}"><div class="requested-dish-actions"><button type="button" class="request-add-dish" data-add-request-after aria-label="Add another requested dish after ${index+1}">＋</button><button type="button" class="request-remove-dish" data-remove-request-row aria-label="Remove requested dish ${index+1}">−</button></div></div>`;
  const renumberRequestRows=()=>{
    [...(requestRows?.querySelectorAll('[data-request-row]')||[])].forEach((r,i)=>{
      const n=r.querySelector('.requested-dish-number'),input=r.querySelector('input'),add=r.querySelector('[data-add-request-after]'),remove=r.querySelector('[data-remove-request-row]');
      if(n)n.textContent=String(i+1);
      if(input)input.setAttribute('aria-label',`Requested dish ${i+1}`);
      if(add)add.setAttribute('aria-label',`Add another requested dish after ${i+1}`);
      if(remove)remove.setAttribute('aria-label',`Remove requested dish ${i+1}`);
    });
  };
  const bindRequestRow=(row)=>{
    if(!row)return;
    row.querySelector('[data-add-request-after]')?.addEventListener('click',()=>{
      const rows=[...requestRows.querySelectorAll('[data-request-row]')];
      if(rows.length>=20){alert('Please request no more than 20 dishes.');return;}
      row.insertAdjacentHTML('afterend',requestRowHtml('',rows.indexOf(row)+1));
      const added=row.nextElementSibling;bindRequestRow(added);renumberRequestRows();added?.querySelector('input')?.focus();
    });
    row.querySelector('[data-remove-request-row]')?.addEventListener('click',()=>{
      const rows=[...requestRows.querySelectorAll('[data-request-row]')];
      if(rows.length===1){const input=row.querySelector('input');if(input)input.value='';return;}
      row.remove();renumberRequestRows();
    });
  };
  const renderRequestRows=(values)=>{
    if(!requestRows)return;
    const dishes=(Array.isArray(values)?values:[]).slice(0,20);
    if(!dishes.length)dishes.push('');
    requestRows.innerHTML=dishes.map((value,index)=>requestRowHtml(value,index)).join('');
    requestRows.querySelectorAll('[data-request-row]').forEach(bindRequestRow);
    renumberRequestRows();
  };
  document.querySelector('[data-open-request-dialog]')?.addEventListener('click',()=>{renderRequestRows(DraftStore.load().requested_dishes);requestDialog?.showModal();window.setTimeout(()=>requestRows?.querySelector('input')?.focus(),60);});
  document.querySelector('[data-add-request-row]')?.addEventListener('click',()=>{
    if(!requestRows)return;
    const rows=[...requestRows.querySelectorAll('[data-request-row]')];
    if(rows.length>=20){alert('Please request no more than 20 dishes.');return;}
    requestRows.insertAdjacentHTML('beforeend',requestRowHtml('',rows.length));
    const row=requestRows.lastElementChild;bindRequestRow(row);renumberRequestRows();row?.querySelector('input')?.focus();
  });
  document.querySelector('[data-save-requests]')?.addEventListener('click',()=>{
    const lines=[...(requestRows?.querySelectorAll('input')||[])].map(input=>String(input.value||'').replace(/\s+/g,' ').trim()).filter(Boolean), unique=[], seen=new Set();
    for(const line of lines){const key=line.toLowerCase();if(!seen.has(key)){seen.add(key);unique.push(line.slice(0,180));}}
    if(unique.length>20){alert('Please request no more than 20 dishes.');return;}
    DraftStore.setRequestedDishes(unique);updateRequestCount();requestDialog?.close();
  });
  requestDialog?.addEventListener('click',e=>{if(e.target===requestDialog)requestDialog.close();});
  document.querySelector('[data-open-menu-filter]')?.addEventListener('click',()=>filterDialog?.showModal());
  filterDialog?.addEventListener('click',e=>{if(e.target===filterDialog)filterDialog.close();});
  document.querySelector('[data-open-category-panel]')?.addEventListener('click',()=>categoryDialog?.showModal());
  document.querySelector('[data-close-category-panel]')?.addEventListener('click',()=>categoryDialog?.close());
  categoryDialog?.addEventListener('click',e=>{if(e.target===categoryDialog)categoryDialog.close();});
  document.querySelectorAll('[data-close-combo]').forEach(btn=>btn.addEventListener('click',()=>comboDialog?.close()));
  document.querySelectorAll('[data-close-item-details]').forEach(btn=>btn.addEventListener('click',()=>document.querySelector('[data-item-details-dialog]')?.close()));
  document.querySelector('[data-item-details-dialog]')?.addEventListener('click',e=>{if(e.target.matches('[data-item-details-dialog]'))e.target.close();});
  comboDialog?.addEventListener('click',e=>{if(e.target===comboDialog)comboDialog.close();});
  document.querySelectorAll('[data-close-biryani-style]').forEach(btn=>btn.addEventListener('click',()=>biryaniDialog?.close()));
  biryaniDialog?.addEventListener('click',e=>{if(e.target===biryaniDialog)biryaniDialog.close();});
  biryaniDialog?.querySelectorAll('[data-biryani-style]').forEach(btn=>btn.addEventListener('click',()=>{if(!pendingBiryaniItem)return;DraftStore.setItemVariant(pendingBiryaniItem.id,btn.dataset.biryaniStyle||'');pendingBiryaniItem=null;biryaniDialog.close();render();updateBasketBar();}));

  function visibleMenus(){return selectedMenu===null?data:data.filter(m=>m.id===selectedMenu);}
  function buildCategories(){
    const categories=new Map();
    visibleMenus().forEach(menu=>menu.categories.forEach(category=>{
      let cat=categories.get(category.name);
      if(!cat){cat={id:`cat-${categories.size}`,name:category.name,subs:new Map()};categories.set(category.name,cat);}
      category.subcategories.forEach(sub=>{
        const isBiryaniCategory=String(category.name||'').trim().toLowerCase()==="biryani's";
        const subKey=isBiryaniCategory?'Biryani':sub.name;
        let targetSub=cat.subs.get(subKey);
        if(!targetSub){targetSub={id:isBiryaniCategory?'biryani-style':sub.id,name:subKey,items:new Map(),sort_order:sub.sort_order,heading_color:sub.heading_color||'#94A3B8'};cat.subs.set(subKey,targetSub);}
        sub.items.forEach(item=>{
          const matchesDiet=selectedDiet==='combo'||item.dietary===selectedDiet||item.dietary==='both';
          const haystack=(item.name+' '+(item.description||'')+' '+category.name+' '+sub.name).toLowerCase();
          const matchesSearch=!searchTerm||haystack.includes(searchTerm);
          if(!matchesDiet||!matchesSearch)return;
          const itemKey=isBiryaniCategory?String(item.name||'').trim().toLowerCase():item.id;
          if(!targetSub.items.has(itemKey)){targetSub.items.set(itemKey,{...item,menu:menu.name,category:category.name,subcategory:subKey});if(item.heading_color)targetSub.heading_color=item.heading_color;}
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

  const menuRoot=document.querySelector('[data-menu-root]');
  const toolbar=document.querySelector('.customer-menu-toolbar');
  const searchInput=document.querySelector('[data-menu-search]');
  const enterSearchMode=()=>{
    if(searchMode)return;
    searchMode=true;
    // Add a same-page history entry so the phone/browser Back button exits
    // search mode first instead of navigating away from /menu.
    if(!history.state?.menuSearch){
      history.pushState({...history.state,menuSearch:true},'',location.href);
    }
    menuRoot?.classList.add('menu-search-mode');
    window.requestAnimationFrame(()=>{if(toolbar){const y=toolbar.getBoundingClientRect().top+window.scrollY;window.scrollTo({top:Math.max(0,y),behavior:'smooth'});}});
    render();
  };
  const exitSearchMode=(fromHistory=false)=>{
    searchMode=false;searchTerm='';
    if(searchInput)searchInput.value='';
    menuRoot?.classList.remove('menu-search-mode');
    searchInput?.blur();
    render();
    // The visible back button should consume the temporary search history
    // entry too, keeping /menu as the current page.
    if(!fromHistory&&history.state?.menuSearch){history.back();}
  };
  window.addEventListener('popstate',()=>{
    if(searchMode&&!history.state?.menuSearch){exitSearchMode(true);}
  });
  const buildSearchItems=()=>{
    const results=new Map();
    visibleMenus().forEach(menu=>menu.categories.forEach(category=>category.subcategories.forEach(sub=>sub.items.forEach(item=>{
      const haystack=(item.name+' '+(item.description||'')+' '+category.name+' '+sub.name+' '+menu.name).toLowerCase();
      const matchesDiet=selectedDiet==='combo'||item.dietary===selectedDiet||item.dietary==='both';
      const isBiryani=String(category.name||'').trim().toLowerCase()==="biryani's";
      const resultKey=isBiryani?`biryani:${String(item.name||'').trim().toLowerCase()}`:`id:${item.id}`;
      if(matchesDiet&&searchTerm&&haystack.includes(searchTerm)&&!results.has(resultKey))results.set(resultKey,{...item,menu:menu.name,category:category.name,subcategory:isBiryani?'Biryani':sub.name});
    }))));
    return [...results.values()];
  };

  function isBiryaniItem(item){return String(item?.category||'').trim().toLowerCase()==="biryani's";}
  function handleAddItem(item){
    if(!item)return;
    const state=DraftStore.load();
    const selected=state.item_ids.includes(Number(item.id));
    if(selected){DraftStore.toggleItem(item.id);render();updateBasketBar();return;}
    if(isBiryaniItem(item)){pendingBiryaniItem=item;if(biryaniTitle)biryaniTitle.textContent=`Choose ${item.name} Style`;biryaniDialog?.showModal();return;}
    DraftStore.toggleItem(item.id);render();updateBasketBar();showComboSuggestions(item.id);
  }

  function render(){
    regionBtns.forEach(b=>b.classList.toggle('active',b.dataset.menuChoice==='all'?selectedMenu===null:Number(b.dataset.menuChoice)===selectedMenu));
    dietBtns.forEach(b=>b.classList.toggle('active',b.dataset.dietChoice===selectedDiet));
    const cats=buildCategories();
    if(searchMode){
      const draft=DraftStore.load();
      const results=buildSearchItems();
      categoryTabs.innerHTML='';
      if(currentCategoryLabel)currentCategoryLabel.textContent='Browse Menu';
      content.innerHTML=searchTerm
        ? `<section class="search-results-section"><div class="search-results-head"><div><div class="eyebrow">Search Results</div><h2>${results.length?`${results.length} Dish${results.length===1?'':'es'} Found`:'No Dishes Found'}</h2></div>${results.length?`<span class="muted">Tap + to add</span>`:''}</div><div class="menu-list search-result-list">${results.map(i=>itemCard(i,draft.item_ids.includes(i.id))).join('')}</div>${results.length?'':`<div class="empty search-empty"><strong>No menu dishes match “${escapeHtml(searchTerm)}”.</strong><span>Try another dish name or return to the full menu.</span></div>`}</section>`
        : '<div class="search-start-state"><div class="search-start-icon">⌕</div><h2>Search The Menu</h2><p>Start typing a dish name such as Biriyani, Paneer, Naan or Dosa.</p></div>';
      content.querySelectorAll('[data-add-item]').forEach(btn=>btn.addEventListener('click',()=>{
        const id=Number(btn.dataset.addItem);handleAddItem(itemMap.get(id));
      }));
      bindMenuCardSelection();bindItemDetails();updateBasketBar();
      return;
    }
    if(!activeCategory||!cats.some(c=>c.id===activeCategory))activeCategory=cats[0]?.id||null;

    const syncCategoryUI=()=>{
      categoryTabs.querySelectorAll('button').forEach(x=>{
        const on=x.dataset.cat===activeCategory;
        x.classList.toggle('active',on);
        x.setAttribute('aria-pressed',String(on));
      });
      const current=cats.find(c=>c.id===activeCategory);
      if(currentCategoryLabel)currentCategoryLabel.textContent=current?.name||'Browse Menu';
    };

    const tabSelected=new Set(DraftStore.load().item_ids||[]);
    const categorySelectedCount=c=>c.subs.reduce((total,sub)=>total+sub.items.filter(item=>tabSelected.has(Number(item.id))).length,0);
    categoryTabs.innerHTML=cats.map(c=>{const count=categorySelectedCount(c);return `<button type="button" data-cat="${c.id}" class="${c.id===activeCategory?'active':''}" aria-pressed="${c.id===activeCategory?'true':'false'}"><span>${escapeHtml(c.name)}</span>${count?`<span class="category-selected-count" aria-label="${count} selected">${count}</span>`:''}</button>`}).join('');
    syncCategoryUI();

    categoryTabs.querySelectorAll('button').forEach(btn=>btn.addEventListener('click',()=>{
      activeCategory=btn.dataset.cat;
      categoryLockUntil=Date.now()+1100;
      syncCategoryUI();
      categoryDialog?.close();
      const target=document.getElementById(activeCategory);
      if(target){
        const y=target.getBoundingClientRect().top+window.scrollY-154;
        window.scrollTo({top:Math.max(0,y),behavior:'smooth'});
        window.setTimeout(()=>{
          if(Date.now()>=categoryLockUntil)updateCategoryFromScroll();
        },1150);
      }
    }));

    const draft=DraftStore.load();
    content.innerHTML=cats.map(c=>`<section class="menu-section" id="${c.id}" data-category-section="${c.id}"><div class="menu-section-title"><h2>${escapeHtml(c.name)}</h2><span class="muted">${c.subs.reduce((n,sub)=>n+sub.items.length,0)} choices</span></div>${c.subs.map(sub=>`<div class="menu-subsection"><div class="subcategory-title" style="--heading-color:${safeHeadingColor(sub.heading_color)}">${escapeHtml(sub.name)}</div><div class="menu-list">${sub.items.map(i=>itemCard(i,draft.item_ids.includes(i.id))).join('')}</div></div>`).join('')}</section>`).join('')||'<div class="empty">No items match these filters.</div>';

    const updateCategoryFromScroll=()=>{
      if(Date.now()<categoryLockUntil)return;
      const sections=[...content.querySelectorAll('[data-category-section]')];
      if(!sections.length)return;
      const anchor=window.scrollY+Math.min(180,Math.max(100,window.innerHeight*.22));
      let current=sections[0];
      for(const section of sections){
        const top=section.getBoundingClientRect().top+window.scrollY;
        if(top<=anchor)current=section;else break;
      }
      const id=current?.dataset.categorySection;
      if(id&&id!==activeCategory){activeCategory=id;syncCategoryUI();}
    };

    if(categoryScrollHandler)window.removeEventListener('scroll',categoryScrollHandler);
    categoryScrollHandler=()=>{
      if(categoryScrollRaf)return;
      categoryScrollRaf=requestAnimationFrame(()=>{categoryScrollRaf=0;updateCategoryFromScroll();});
    };
    window.addEventListener('scroll',categoryScrollHandler,{passive:true});
    updateCategoryFromScroll();

    content.querySelectorAll('[data-add-item]').forEach(btn=>btn.addEventListener('click',()=>{
      const id=Number(btn.dataset.addItem);handleAddItem(itemMap.get(id));
    }));
    bindMenuCardSelection();bindItemDetails();updateBasketBar();
  }
  function itemCard(i,selected){
    const neutral=['welcome drink','desserts','add ons'].includes(String(i.category||'').trim().toLowerCase());
    const label=i.dietary==='veg'?'Veg':i.dietary==='nonveg'?'Non Veg':'Both';
    const dietary=neutral?'':`<div class="diet-dot ${escapeHtml(i.dietary)}">${label}</div>`;
    const comment=DraftStore.load().item_comments?.[String(i.id)]||'';
    return `<article class="menu-item ${selected?'selected':''} ${i.image_url?'has-image':''} ${neutral?'dietary-card-neutral':'dietary-card-'+escapeHtml(i.dietary)}" data-item-card="${i.id}">${i.image_url?`<img class="menu-item-image" src="${escapeHtml(i.image_url)}" alt="${escapeHtml(i.name)}" loading="lazy">`:''}<div class="menu-item-copy"><div class="menu-item-name">${escapeHtml(i.name)}</div>${comment?`<div class="item-comment-preview">Note: ${escapeHtml(comment)}</div>`:''}${i.price!=null?`<div class="menu-item-price">${formatMenuPrice(i.price)}</div>`:''}${dietary}</div><div class="menu-item-actions"><div class="menu-item-action-top"><button type="button" class="item-details-btn" data-item-details="${i.id}" aria-label="View details for ${escapeHtml(i.name)}">Details</button><button type="button" class="add-btn ${selected?'active':''}" aria-label="${selected?'Remove':'Add'} ${escapeHtml(i.name)}" data-add-item="${i.id}">${selected?'✓':'+'}</button></div><button type="button" class="item-comment-btn ${comment?'has-comment':''}" data-item-comment="${i.id}" aria-label="Add comment for ${escapeHtml(i.name)}">${comment?'Comment ✓':'Comment'}</button></div></article>`;
  }
  function bindMenuCardSelection(){
    content.querySelectorAll('[data-item-card]').forEach(card=>card.addEventListener('click',e=>{
      if(e.target.closest('button,a,input,textarea,select,label,[role="button"]'))return;
      const item=itemMap.get(Number(card.dataset.itemCard));
      handleAddItem(item);
    }));
  }
  function bindItemDetails(){
    content.querySelectorAll('[data-item-details]').forEach(btn=>btn.addEventListener('click',()=>{
      const i=itemMap.get(Number(btn.dataset.itemDetails));if(!i)return;
      const d=document.querySelector('[data-item-details-dialog]');if(!d)return;
      d.querySelector('[data-item-details-title]').textContent=i.name;
      d.querySelector('[data-item-details-copy]').textContent=i.description||'Food description will be added soon.';
      d.querySelector('[data-item-details-allergens]').textContent=i.allergens||'Contact Spice India to confirm recipe allergens before ordering.';
      const img=d.querySelector('[data-item-details-image]');
      const placeholder=d.querySelector('[data-item-details-image-placeholder]');
      if(i.image_url){img.src=i.image_url;img.alt=i.name;img.hidden=false;placeholder.hidden=true;}else{img.removeAttribute('src');img.alt='';img.hidden=true;placeholder.hidden=false;}
      d.showModal();
    }));
    content.querySelectorAll('[data-item-comment]').forEach(btn=>btn.addEventListener('click',()=>{const i=itemMap.get(Number(btn.dataset.itemComment));const d=document.querySelector('[data-item-comment-dialog]');if(!i||!d)return;d.dataset.itemId=String(i.id);d.querySelector('[data-item-comment-title]').textContent=i.name;const input=d.querySelector('[data-item-comment-input]');input.value=DraftStore.load().item_comments?.[String(i.id)]||'';d.showModal();}));
  }
  regionBtns.forEach(b=>b.addEventListener('click',()=>{selectedMenu=b.dataset.menuChoice==='all'?null:Number(b.dataset.menuChoice);activeCategory=null;render();}));
  dietBtns.forEach(b=>b.addEventListener('click',()=>{selectedDiet=b.dataset.dietChoice;activeCategory=null;render();if(b.closest('[data-menu-filter-dialog]'))filterDialog?.close();}));
  searchInput?.addEventListener('focus',enterSearchMode);
  searchInput?.addEventListener('input',()=>{if(!searchMode)enterSearchMode();searchTerm=String(searchInput.value||'').trim().toLowerCase();render();});
  searchInput?.addEventListener('search',()=>{searchTerm=String(searchInput.value||'').trim().toLowerCase();searchInput.blur();render();});
  searchInput?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();searchTerm=String(searchInput.value||'').trim().toLowerCase();searchInput.blur();render();}});
  document.querySelector('[data-exit-search]')?.addEventListener('click',exitSearchMode);
  updateRequestCount();render();
}

function updateBasketBar(){const n=DraftStore.load().item_ids.length;document.querySelectorAll('[data-cart-count]').forEach(badge=>{badge.textContent=String(n);badge.classList.toggle('empty',n===0);});const basket=document.querySelector('[data-menu-basket]');if(basket){basket.hidden=n===0;}document.body.classList.toggle('menu-has-basket',n>0);const legacy=document.querySelector('[data-basket-count]');if(legacy)legacy.textContent=formatCount(n);}

function initReview(){
  const root=document.querySelector('[data-review-root]');if(!root)return;
  const itemsBox=document.querySelector('[data-review-items]'),requestsBox=document.querySelector('[data-review-requests]'),notesInput=document.querySelector('[data-customer-notes]'),continueBtn=document.querySelector('[data-continue-details]');
  const draft=DraftStore.load();
  if(notesInput){notesInput.value=draft.customer_notes||'';notesInput.addEventListener('input',()=>DraftStore.setCustomerNotes(notesInput.value));}
  const renderRequests=state=>{const requests=state.requested_dishes||[];requestsBox.innerHTML=requests.length?`<div class="requested-dish-list">${requests.map(name=>`<div class="requested-dish-row"><strong>${escapeHtml(name)}</strong><span class="request-status pending">Needs Confirmation</span></div>`).join('')}</div>`:'<div class="empty">No extra dishes requested.</div>';};
  const updateAvailability=state=>{if(continueBtn)continueBtn.disabled=!((state.item_ids||[]).length||(state.requested_dishes||[]).length);};
  renderRequests(draft);updateAvailability(draft);renderReviewItems(draft.item_ids,itemsBox,null,draft.requested_dishes.length);
  window.addEventListener('draftchange',e=>{const state=e.detail||DraftStore.load();renderRequests(state);updateAvailability(state);renderReviewItems(state.item_ids||[],itemsBox,null,(state.requested_dishes||[]).length);});
  continueBtn?.addEventListener('click',()=>{const state=DraftStore.load();if(!(state.item_ids.length||state.requested_dishes.length))return;location.href='/order?next=/submit';});
}
async function renderReviewItems(ids,box,submit,requestedCount=0){
  if(!ids.length){box.innerHTML='<div class="empty">No standard menu items selected. <a href="/menu"><strong>Choose Menu Items</strong></a></div>';if(submit)submit.disabled=requestedCount===0;return;}
  try{const res=await fetch('/api/menu-items?ids='+encodeURIComponent(ids.join(','))),items=await res.json(),groups={};items.forEach(i=>{(((groups[i.menu]??={})[i.category]??={})[i.subcategory]??=[]).push(i)});
    box.innerHTML=Object.entries(groups).map(([m,cats])=>`<div class="review-group"><h3>${escapeHtml(m)}</h3>${Object.entries(cats).map(([c,subs])=>{let counter=1;const catCount=Object.values(subs).reduce((n,arr)=>n+arr.length,0);return `<div class="review-category review-category-highlight">${escapeHtml(c)} <span>× ${catCount}</span></div>${Object.entries(subs).map(([s,arr])=>`${s!=='Main Selection'?`<div class="help">${escapeHtml(s)}</div>`:''}<ol class="review-numbered-list review-basket-list" start="${counter}">${arr.map(i=>`<li class="dietary-list-item review-basket-item ${escapeHtml(i.dietary)}">${i.image_url?`<img class="review-basket-image" src="${escapeHtml(i.image_url)}" alt="${escapeHtml(i.name)}" loading="lazy" onerror="this.style.display='none'">`:`<div class="review-basket-image review-basket-placeholder" aria-hidden="true">SI</div>`}<span class="review-basket-copy"><strong>${escapeHtml(i.name)}</strong>${DraftStore.load().item_variants?.[String(i.id)]?`<small class="review-item-variant">Style: ${escapeHtml(DraftStore.load().item_variants[String(i.id)])}</small>`:''}${DraftStore.load().item_comments?.[String(i.id)]?`<small class="review-item-comment">Your comment: ${escapeHtml(DraftStore.load().item_comments[String(i.id)])}</small>`:''}${i.description?`<small>${escapeHtml(i.description)}</small>`:''}${i.price!=null?`<strong class="review-item-price">${formatMenuPrice(i.price)}</strong>`:''}</span><button type="button" data-remove="${i.id}">Remove</button></li>`).join('')}</ol>${(()=>{counter+=arr.length;return ''})()}`).join('')}`}).join('')}</div>`).join('');
    box.querySelectorAll('[data-remove]').forEach(b=>b.addEventListener('click',()=>DraftStore.removeItem(Number(b.dataset.remove))));if(submit)submit.disabled=false;
  }catch{box.innerHTML='<div class="notice error">Could not load your selected items. Return to the menu and try again.</div>';if(submit)submit.disabled=true;}
}

function initItemCommentDialog(){
  const d=document.querySelector('[data-item-comment-dialog]');if(!d)return;
  const input=d.querySelector('[data-item-comment-input]');
  d.querySelectorAll('[data-close-item-comment]').forEach(b=>b.addEventListener('click',()=>d.close()));
  d.querySelector('[data-save-item-comment]')?.addEventListener('click',()=>{
    const id=Number(d.dataset.itemId);if(!id)return;
    const state=DraftStore.setItemComment(id,input.value);const comment=state.item_comments?.[String(id)]||'';d.close();
    document.querySelectorAll(`[data-item-comment="${id}"]`).forEach(btn=>{btn.textContent=comment?'Comment ✓':'Comment';btn.classList.toggle('has-comment',Boolean(comment));const card=btn.closest('.menu-item');if(card){const selected=state.item_ids.includes(id);card.classList.toggle('selected',selected);let preview=card.querySelector('.item-comment-preview');if(comment){if(!preview){preview=document.createElement('div');preview.className='item-comment-preview';card.querySelector('.menu-item-name')?.insertAdjacentElement('afterend',preview);}preview.textContent='Note: '+comment;}else preview?.remove();const add=card.querySelector(`[data-add-item="${id}"]`);if(add){add.textContent=selected?'✓':'+';add.classList.toggle('active',selected);add.setAttribute('aria-label',(selected?'Remove ':'Add ')+(card.querySelector('.menu-item-name')?.textContent||'item'));}}});
    updateBasketBar();
  });
  d.addEventListener('click',e=>{if(e.target===d)d.close();});
}

function initAllergyInfo(){
  const d=document.querySelector('[data-allergy-info-dialog]');if(!d)return;
  document.querySelectorAll('[data-open-allergy-info]').forEach(btn=>btn.addEventListener('click',()=>d.showModal()));
  d.querySelectorAll('[data-close-allergy-info]').forEach(btn=>btn.addEventListener('click',()=>d.close()));
  d.addEventListener('click',e=>{if(e.target===d)d.close();});
}

function initDraftControls(){document.querySelectorAll('[data-clear-draft]').forEach(btn=>btn.addEventListener('click',()=>{if(confirm('Clear your saved catering draft?')){DraftStore.clear();location.href='/';}}));const recent=document.querySelector('[data-recent-order]');if(recent){const t=localStorage.getItem('lastCateringOrderToken');if(t){recent.href='/orders/'+t;recent.hidden=false;}}}
document.addEventListener('DOMContentLoaded',()=>{initDetailsForm();initMenu();initReview();initItemCommentDialog();initAllergyInfo();initDraftControls();updateBasketBar();});
