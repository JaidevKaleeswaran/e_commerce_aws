/**
 * Elite E-Commerce — Main Application Shell
 * Clean · Minimal · Professional
 */

import { store } from './core/store/appStore.js';

// === GLOBAL EVENT HANDLERS ===

window.S = {
  go: v => store.go(v),
  openCart: () => store.openCart(),
  closeCart: () => store.closeCart(),
  openSearch: () => store.openSearch(),
  closeSearch: () => store.closeSearch(),
  openProduct: id => store.openProduct(id),
  closeProduct: () => store.closeProduct(),
  selectVariant: id => store.selectVariant(id),
  addToCart: (id, vid) => { const p = store.state.products.find(x => x.id === id); if (p) store.addToCart(p, vid); },
  updateQty: (k, d) => store.updateQty(k, d),
  removeItem: k => store.removeItem(k),
  applyCoupon: () => { const el = document.getElementById('coupon-input'); if (el) store.applyCoupon(el.value); },
  setFilter: (k, v) => store.setFilter(k, v),
  setField: (k, v) => store.setCheckoutField(k, v),
  setStep: n => store.setCheckoutStep(n),
  placeOrder: () => store.placeOrder(),
  toggleTheme: () => store.toggleTheme(),
  search: v => store.setFilter('search', v)
};

// Cmd+K
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); store.state.searchOpen ? store.closeSearch() : store.openSearch(); }
  if (e.key === 'Escape') { store.closeSearch(); store.closeCart(); store.closeProduct(); }
});

// === RENDER ===

function render(s) {
  const root = document.getElementById('app');
  if (!root) return;
  root.innerHTML = `
    ${renderNav(s)}
    <main style="min-height: calc(100vh - 200px);">${renderView(s)}</main>
    ${renderFooter()}
    ${renderCartDrawer(s)}
    ${renderSearchModal(s)}
    ${renderProductModal(s)}
    ${renderToasts(s)}
  `;
}

// === HEADER ===

function renderNav(s) {
  const count = s.cart.reduce((a, i) => a + i.qty, 0);
  return `
  <header style="position: sticky; top: 0; z-index: 100; background: var(--bg-white); border-bottom: 1px solid var(--border-light);">
    <div style="max-width: 1200px; margin: 0 auto; padding: 0 var(--space-lg); height: 64px; display: flex; align-items: center; justify-content: space-between;">
      <a href="#" onclick="S.go('home'); return false" style="font-size: 1.125rem; font-weight: 700; letter-spacing: -0.03em;">AURA</a>
      <nav style="display: flex; align-items: center; gap: var(--space-xl);" class="hide-mobile">
        <a href="#" onclick="S.go('home'); return false" style="font-size: 0.875rem; font-weight: 500; color: ${s.view==='home'?'var(--text-primary)':'var(--text-secondary)'};">Home</a>
        <a href="#" onclick="S.go('catalog'); return false" style="font-size: 0.875rem; font-weight: 500; color: ${s.view==='catalog'?'var(--text-primary)':'var(--text-secondary)'};">Products</a>
      </nav>
      <div style="display: flex; align-items: center; gap: var(--space-sm);">
        <button class="btn btn-ghost btn-icon" onclick="S.openSearch()" title="Search (⌘K)">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        </button>
        <button class="btn btn-ghost btn-icon" onclick="S.toggleTheme()" title="Toggle theme">
          ${s.theme === 'dark'
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>'
          }
        </button>
        <button class="btn btn-ghost btn-icon" onclick="S.openCart()" title="Cart" style="position: relative;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
          ${count > 0 ? `<span style="position: absolute; top: 4px; right: 4px; width: 16px; height: 16px; border-radius: 50%; background: var(--accent); color: var(--text-inverse); font-size: 0.625rem; font-weight: 600; display: flex; align-items: center; justify-content: center;">${count}</span>` : ''}
        </button>
      </div>
    </div>
  </header>`;
}

// === VIEW ROUTER ===

function renderView(s) {
  switch (s.view) {
    case 'catalog': return renderCatalog(s);
    case 'checkout': return renderCheckout(s);
    case 'confirmation': return renderConfirmation(s);
    default: return renderHome(s);
  }
}

// === HOME ===

function renderHome(s) {
  const featured = s.products.filter(p => p.badge === 'New');
  return `
  <section style="max-width: 1200px; margin: 0 auto; padding: var(--space-4xl) var(--space-lg);">
    <div style="text-align: center; max-width: 640px; margin: 0 auto var(--space-3xl);">
      <h1 style="font-size: clamp(2rem, 4vw, 3rem); font-weight: 700; margin-bottom: var(--space-md);">Designed for the way you work.</h1>
      <p style="font-size: 1.125rem; color: var(--text-secondary); margin-bottom: var(--space-xl);">Premium technology, thoughtfully crafted.</p>
      <button class="btn btn-primary btn-lg" onclick="S.go('catalog')">Browse all products</button>
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--space-lg);">
      ${s.products.slice(0, 4).map(p => productCard(p)).join('')}
    </div>
  </section>`;
}

// === CATALOG ===

function renderCatalog(s) {
  let items = [...s.products];
  if (s.filter.category !== 'all') items = items.filter(p => p.category === s.filter.category);
  if (s.filter.search) { const q = s.filter.search.toLowerCase(); items = items.filter(p => p.name.toLowerCase().includes(q) || p.category.toLowerCase().includes(q)); }
  if (s.filter.sort === 'price-asc') items.sort((a, b) => a.price - b.price);
  else if (s.filter.sort === 'price-desc') items.sort((a, b) => b.price - a.price);

  return `
  <section style="max-width: 1200px; margin: 0 auto; padding: var(--space-2xl) var(--space-lg);">
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-xl); flex-wrap: wrap; gap: var(--space-md);">
      <h1 style="font-size: 1.5rem; font-weight: 600;">Products</h1>
      <div style="display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap;">
        ${['all', ...s.categories.map(c => c.id)].map(id => `
          <button class="btn ${s.filter.category === id ? 'btn-primary' : 'btn-secondary'} btn-sm" onclick="S.setFilter('category','${id}')">${id === 'all' ? 'All' : s.categories.find(c=>c.id===id)?.name || id}</button>
        `).join('')}
        <select class="input" style="width: auto; padding: 6px 12px; font-size: 0.8125rem;" onchange="S.setFilter('sort', this.value)">
          <option value="default">Sort by</option>
          <option value="price-asc">Price: Low → High</option>
          <option value="price-desc">Price: High → Low</option>
        </select>
      </div>
    </div>
    ${items.length === 0 ? `
      <div style="text-align: center; padding: var(--space-4xl) 0; color: var(--text-secondary);">
        <p style="font-size: 1.125rem; margin-bottom: var(--space-md);">No products found</p>
        <button class="btn btn-secondary" onclick="S.setFilter('category','all')">Clear filters</button>
      </div>
    ` : `
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--space-lg);">
        ${items.map(p => productCard(p)).join('')}
      </div>
    `}
  </section>`;
}

// === PRODUCT CARD ===

function productCard(p) {
  return `
  <div class="card" style="cursor: pointer;" onclick="S.openProduct('${p.id}')">
    <div style="aspect-ratio: 1; background: var(--bg-subtle); overflow: hidden; position: relative;">
      <img src="${p.images[0]}" alt="${p.name}" style="width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s;" onmouseenter="this.style.transform='scale(1.03)'" onmouseleave="this.style.transform='scale(1)'" loading="lazy" />
      ${p.badge ? `<span class="badge" style="position: absolute; top: 12px; left: 12px;">${p.badge}</span>` : ''}
    </div>
    <div style="padding: var(--space-md);">
      <p style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 2px; text-transform: uppercase; letter-spacing: 0.05em;">${p.category}</p>
      <h3 style="font-size: 0.9375rem; font-weight: 600; margin-bottom: 2px;">${p.name}</h3>
      <p style="font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: var(--space-sm);">${p.subtitle}</p>
      <p style="font-size: 0.9375rem; font-weight: 600;">$${p.price.toLocaleString()}</p>
    </div>
  </div>`;
}

// === PRODUCT MODAL ===

function renderProductModal(s) {
  if (!s.productModal) return '';
  const p = s.products.find(x => x.id === s.productModal);
  if (!p) return '';
  const v = p.variants.find(x => x.id === s.selectedVariant) || p.variants[0];
  const price = p.price + v.priceOffset;

  return `
  <div class="overlay active" onclick="S.closeProduct()"></div>
  <div class="modal active product-modal" style="max-width: 1000px; width: 95vw; padding: 0; overflow: hidden;" onclick="event.stopPropagation()">
    <div style="display: grid; grid-template-columns: 1fr 1.4fr;" class="catalog-grid">
      <div style="background: var(--bg-subtle); display: flex; align-items: center; justify-content: center; padding: var(--space-md); position: relative;">
        <img src="${p.images[0]}" alt="${p.name}" style="max-width: 100%; max-height: 380px; width: auto; height: auto; object-fit: contain; border-radius: var(--radius-md);" />
        ${p.badge ? `<span class="badge" style="position: absolute; top: 12px; left: 12px;">${p.badge}</span>` : ''}
      </div>
      <div style="padding: var(--space-lg); display: flex; flex-direction: column; justify-content: space-between;">
        <div>
          <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-sm); margin-bottom: 0;">
            <div>
              <p style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">${p.category}</p>
              <h2 style="font-size: 1.375rem; font-weight: 700; color: var(--text-primary); line-height: 1.1;">${p.name}</h2>
            </div>
            <button class="btn btn-ghost btn-icon" onclick="S.closeProduct()" style="flex-shrink: 0; margin-top: -6px; margin-right: -6px;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>

          <p style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary); margin-top: 4px; margin-bottom: var(--space-sm);">$${price.toLocaleString()}</p>
          <p style="font-size: 0.8125rem; color: var(--text-secondary); line-height: 1.4; margin-bottom: var(--space-md); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${p.description}</p>

          <div style="margin-bottom: var(--space-sm);">
            <p class="label" style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Select Option</p>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              ${p.variants.map(vr => `
                <button class="btn ${vr.id === v.id ? 'btn-primary' : 'btn-secondary'} btn-sm" style="padding: 4px 10px; font-size: 0.75rem;" onclick="S.selectVariant('${vr.id}')">${vr.label}</button>
              `).join('')}
            </div>
          </div>

          <div style="background: var(--bg-subtle); border-radius: var(--radius-md); padding: var(--space-sm) var(--space-md); margin-bottom: var(--space-sm);">
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px 16px;">
              ${Object.entries(p.specs).map(([k, val]) => `
                <div style="font-size: 0.75rem; display: flex; justify-content: space-between;">
                  <span style="color: var(--text-muted);">${k}</span>
                  <span style="font-weight: 600; color: var(--text-primary); text-align: right;">${val}</span>
                </div>
              `).join('')}
            </div>
          </div>
        </div>

        <div style="margin-top: 4px;">
          <button class="btn btn-primary" style="width: 100%; padding: 10px 16px; font-size: 0.875rem;" onclick="S.addToCart('${p.id}','${v.id}'); S.closeProduct()">Add to cart — $${price.toLocaleString()}</button>
        </div>
      </div>
    </div>
  </div>`;
}

// === CART DRAWER ===

function renderCartDrawer(s) {
  const totals = store.getCartTotals();
  return `
  <div class="overlay ${s.cartOpen ? 'active' : ''}" onclick="S.closeCart()"></div>
  <div class="drawer ${s.cartOpen ? 'active' : ''}">
    <div style="padding: var(--space-lg); border-bottom: 1px solid var(--border-light); display: flex; align-items: center; justify-content: space-between;">
      <h3 style="font-size: 1.125rem; font-weight: 600;">Cart (${totals.itemCount})</h3>
      <button class="btn btn-ghost btn-icon" onclick="S.closeCart()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    </div>

    <div style="flex: 1; overflow-y: auto; padding: var(--space-lg);">
      ${s.cart.length === 0 ? `
        <div style="text-align: center; padding: var(--space-4xl) 0; color: var(--text-muted);">
          <p style="margin-bottom: var(--space-md);">Your cart is empty</p>
          <button class="btn btn-secondary btn-sm" onclick="S.closeCart(); S.go('catalog')">Browse products</button>
        </div>
      ` : s.cart.map(i => `
        <div style="display: flex; gap: var(--space-md); padding-bottom: var(--space-md); margin-bottom: var(--space-md); border-bottom: 1px solid var(--border-light);">
          <img src="${i.image}" alt="${i.name}" style="width: 64px; height: 64px; border-radius: var(--radius-sm); object-fit: cover; background: var(--bg-subtle);" />
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; justify-content: space-between; gap: var(--space-sm);">
              <div>
                <p style="font-size: 0.875rem; font-weight: 500;">${i.name}</p>
                <p style="font-size: 0.75rem; color: var(--text-muted);">${i.variantLabel}</p>
              </div>
              <button class="btn btn-ghost" onclick="S.removeItem('${i.key}')" style="padding: 4px; color: var(--text-muted);">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
              </button>
            </div>
            <div style="display: flex; align-items: center; justify-content: space-between; margin-top: var(--space-sm);">
              <div style="display: flex; align-items: center; border: 1px solid var(--border-default); border-radius: var(--radius-sm); overflow: hidden;">
                <button onclick="S.updateQty('${i.key}', -1)" style="width: 28px; height: 28px; border: none; background: transparent; cursor: pointer; color: var(--text-primary);">−</button>
                <span style="width: 28px; text-align: center; font-size: 0.8125rem; font-weight: 500;">${i.qty}</span>
                <button onclick="S.updateQty('${i.key}', 1)" style="width: 28px; height: 28px; border: none; background: transparent; cursor: pointer; color: var(--text-primary);">+</button>
              </div>
              <span style="font-size: 0.875rem; font-weight: 500;">$${(i.price * i.qty).toLocaleString()}</span>
            </div>
          </div>
        </div>
      `).join('')}
    </div>

    ${s.cart.length > 0 ? `
    <div style="padding: var(--space-lg); border-top: 1px solid var(--border-light);">
      <div style="display: flex; gap: var(--space-sm); margin-bottom: var(--space-md);">
        <input type="text" id="coupon-input" class="input" placeholder="Coupon code" style="font-size: 0.8125rem;" value="${s.coupon?.code || ''}" />
        <button class="btn btn-secondary btn-sm" onclick="S.applyCoupon()">${s.coupon ? '✓' : 'Apply'}</button>
      </div>
      <div style="font-size: 0.875rem; display: flex; flex-direction: column; gap: 6px; margin-bottom: var(--space-md);">
        <div style="display: flex; justify-content: space-between;"><span style="color: var(--text-secondary);">Subtotal</span><span>$${totals.subtotal.toLocaleString()}</span></div>
        ${totals.discount > 0 ? `<div style="display: flex; justify-content: space-between; color: var(--accent-success);"><span>Discount</span><span>−$${totals.discount.toLocaleString()}</span></div>` : ''}
        <div style="display: flex; justify-content: space-between;"><span style="color: var(--text-secondary);">Shipping</span><span>${totals.shipping === 0 ? 'Free' : '$' + totals.shipping}</span></div>
        <div style="display: flex; justify-content: space-between;"><span style="color: var(--text-secondary);">Tax</span><span>$${totals.tax.toFixed(2)}</span></div>
        <div style="display: flex; justify-content: space-between; font-weight: 600; padding-top: var(--space-sm); border-top: 1px solid var(--border-light);"><span>Total</span><span>$${totals.total.toFixed(2)}</span></div>
      </div>
      <button class="btn btn-primary" style="width: 100%;" onclick="S.closeCart(); S.go('checkout')">Checkout</button>
    </div>` : ''}
  </div>`;
}

// === SEARCH MODAL ===

function renderSearchModal(s) {
  if (!s.searchOpen) return '';
  const q = s.filter.search.toLowerCase();
  const results = q ? s.products.filter(p => p.name.toLowerCase().includes(q) || p.category.includes(q)) : s.products.slice(0, 4);

  return `
  <div class="overlay active" onclick="S.closeSearch()"></div>
  <div class="modal active" style="padding: 0; top: 30%;" onclick="event.stopPropagation()">
    <div style="display: flex; align-items: center; gap: var(--space-md); padding: var(--space-md) var(--space-lg); border-bottom: 1px solid var(--border-light);">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
      <input type="text" class="input" style="border: none; padding: 0; background: transparent;" placeholder="Search products…" value="${s.filter.search}" oninput="S.search(this.value)" autofocus />
      <button class="btn btn-ghost btn-sm" onclick="S.closeSearch()" style="font-size: 0.75rem; color: var(--text-muted);">ESC</button>
    </div>
    <div style="padding: var(--space-sm); max-height: 320px; overflow-y: auto;">
      ${results.length === 0 ? `<p style="padding: var(--space-xl); text-align: center; color: var(--text-muted); font-size: 0.875rem;">No results found</p>` : results.map(p => `
        <div onclick="S.closeSearch(); S.openProduct('${p.id}')" style="display: flex; align-items: center; gap: var(--space-md); padding: var(--space-sm) var(--space-md); border-radius: var(--radius-md); cursor: pointer; transition: background var(--duration-fast);" onmouseenter="this.style.background='var(--bg-subtle)'" onmouseleave="this.style.background='transparent'">
          <img src="${p.images[0]}" style="width: 40px; height: 40px; border-radius: var(--radius-sm); object-fit: cover; background: var(--bg-subtle);" />
          <div style="flex: 1;"><p style="font-size: 0.875rem; font-weight: 500;">${p.name}</p><p style="font-size: 0.75rem; color: var(--text-muted);">${p.subtitle}</p></div>
          <span style="font-size: 0.875rem; font-weight: 500;">$${p.price.toLocaleString()}</span>
        </div>
      `).join('')}
    </div>
  </div>`;
}

// === CHECKOUT ===

function renderCheckout(s) {
  const totals = store.getCartTotals();
  if (s.cart.length === 0) return `<section style="max-width: 600px; margin: var(--space-4xl) auto; text-align: center; padding: 0 var(--space-lg);"><h2 style="font-size: 1.5rem; margin-bottom: var(--space-md);">Your cart is empty</h2><button class="btn btn-primary" onclick="S.go('catalog')">Browse products</button></section>`;
  const d = s.checkout;
  const step = s.checkoutStep;

  return `
  <section style="max-width: 960px; margin: 0 auto; padding: var(--space-2xl) var(--space-lg);">
    <button class="btn btn-ghost btn-sm" onclick="S.go('catalog')" style="margin-bottom: var(--space-lg);">← Back to store</button>
    <div style="display: grid; grid-template-columns: 1.2fr 0.8fr; gap: var(--space-2xl);" class="catalog-grid">
      <div>
        ${step === 1 ? `
        <h2 style="font-size: 1.25rem; font-weight: 600; margin-bottom: var(--space-lg);">Shipping</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md);">
          <div><label class="label">First name</label><input class="input" value="${d.firstName}" onchange="S.setField('firstName',this.value)" /></div>
          <div><label class="label">Last name</label><input class="input" value="${d.lastName}" onchange="S.setField('lastName',this.value)" /></div>
        </div>
        <div style="margin-top: var(--space-md);"><label class="label">Email</label><input class="input" type="email" value="${d.email}" onchange="S.setField('email',this.value)" /></div>
        <div style="margin-top: var(--space-md);"><label class="label">Address</label><input class="input" value="${d.address}" onchange="S.setField('address',this.value)" /></div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--space-md); margin-top: var(--space-md);">
          <div><label class="label">City</label><input class="input" value="${d.city}" onchange="S.setField('city',this.value)" /></div>
          <div><label class="label">State</label><input class="input" value="${d.state}" onchange="S.setField('state',this.value)" /></div>
          <div><label class="label">ZIP</label><input class="input" value="${d.zip}" onchange="S.setField('zip',this.value)" /></div>
        </div>
        <button class="btn btn-primary" style="width: 100%; margin-top: var(--space-xl);" onclick="S.setStep(2)">Continue to payment</button>
        ` : `
        <h2 style="font-size: 1.25rem; font-weight: 600; margin-bottom: var(--space-lg);">Payment</h2>
        <div style="margin-bottom: var(--space-md);"><label class="label">Card number</label><input class="input" placeholder="4242 4242 4242 4242" value="${d.cardNumber}" onchange="S.setField('cardNumber',this.value)" /></div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md);">
          <div><label class="label">Expiry</label><input class="input" placeholder="MM / YY" value="${d.cardExp}" onchange="S.setField('cardExp',this.value)" /></div>
          <div><label class="label">CVC</label><input class="input" placeholder="123" value="${d.cardCvc}" onchange="S.setField('cardCvc',this.value)" /></div>
        </div>
        <div style="display: flex; gap: var(--space-sm); margin-top: var(--space-xl);">
          <button class="btn btn-secondary" onclick="S.setStep(1)">Back</button>
          <button class="btn btn-primary" style="flex: 1;" onclick="S.placeOrder()">Place order — $${totals.total.toFixed(2)}</button>
        </div>
        `}
      </div>

      <div style="background: var(--bg-subtle); border-radius: var(--radius-lg); padding: var(--space-lg); height: fit-content;">
        <h4 style="font-size: 0.875rem; font-weight: 600; margin-bottom: var(--space-md);">Order summary</h4>
        ${s.cart.map(i => `
          <div style="display: flex; justify-content: space-between; font-size: 0.8125rem; margin-bottom: var(--space-sm);">
            <span style="color: var(--text-secondary);">${i.name} × ${i.qty}</span>
            <span>$${(i.price * i.qty).toLocaleString()}</span>
          </div>
        `).join('')}
        <div style="border-top: 1px solid var(--border-light); margin-top: var(--space-md); padding-top: var(--space-md); font-size: 0.875rem;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: var(--text-secondary);">Subtotal</span><span>$${totals.subtotal.toLocaleString()}</span></div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: var(--text-secondary);">Shipping</span><span>${totals.shipping === 0 ? 'Free' : '$'+totals.shipping}</span></div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: var(--text-secondary);">Tax</span><span>$${totals.tax.toFixed(2)}</span></div>
          <div style="display: flex; justify-content: space-between; font-weight: 600; padding-top: var(--space-sm); border-top: 1px solid var(--border-light); margin-top: var(--space-sm);"><span>Total</span><span>$${totals.total.toFixed(2)}</span></div>
        </div>
      </div>
    </div>
  </section>`;
}

// === CONFIRMATION ===

function renderConfirmation(s) {
  const o = s.lastOrder;
  if (!o) return `<section style="text-align: center; padding: var(--space-4xl);"><p>No recent order</p></section>`;
  return `
  <section style="max-width: 600px; margin: 0 auto; padding: var(--space-4xl) var(--space-lg); text-align: center;">
    <div style="width: 56px; height: 56px; border-radius: 50%; background: var(--accent-success); display: flex; align-items: center; justify-content: center; margin: 0 auto var(--space-lg);">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
    </div>
    <h1 style="font-size: 1.75rem; font-weight: 600; margin-bottom: var(--space-sm);">Thank you for your order</h1>
    <p style="color: var(--text-secondary); margin-bottom: var(--space-xl);">Order ${o.id} · ${o.date}</p>
    
    <div style="background: var(--bg-subtle); border-radius: var(--radius-lg); padding: var(--space-lg); text-align: left; margin-bottom: var(--space-xl);">
      ${o.items.map(i => `
        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; margin-bottom: var(--space-sm);">
          <span>${i.name} × ${i.qty}</span><span>$${(i.price * i.qty).toLocaleString()}</span>
        </div>
      `).join('')}
      <div style="border-top: 1px solid var(--border-light); padding-top: var(--space-md); margin-top: var(--space-md); display: flex; justify-content: space-between; font-weight: 600;">
        <span>Total</span><span>$${o.total.toFixed(2)}</span>
      </div>
    </div>
    <button class="btn btn-primary" onclick="S.go('home')">Continue shopping</button>
  </section>`;
}

// === FOOTER ===

function renderFooter() {
  return `
  <footer style="border-top: 1px solid var(--border-light); padding: var(--space-2xl) var(--space-lg);">
    <div style="max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem; color: var(--text-muted);">
      <span>© 2026 AURA</span>
      <span>Built on AWS</span>
    </div>
  </footer>`;
}

// === TOASTS ===

function renderToasts(s) {
  if (s.toasts.length === 0) return '';
  return `<div class="toast-stack">${s.toasts.map(t => `
    <div class="toast-item">
      ${t.type === 'error' ? '<span style="color: var(--accent-error);">✕</span>' : '<span style="color: var(--accent-success);">✓</span>'}
      <span>${t.message}</span>
    </div>
  `).join('')}</div>`;
}

// === BOOT ===

store.subscribe(render);
document.addEventListener('DOMContentLoaded', () => render(store.state));
