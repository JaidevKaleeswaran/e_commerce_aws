/**
 * Application State Store
 * Minimal reactive state with localStorage persistence
 */

import { PRODUCTS, CATEGORIES, COUPONS } from '../mock/database.js';

class Store {
  constructor() {
    this.listeners = new Set();
    this.state = {
      view: 'home',
      theme: localStorage.getItem('theme') || 'light',
      products: PRODUCTS,
      categories: CATEGORIES,
      coupons: COUPONS,

      // Filters
      filter: { category: 'all', search: '', sort: 'default' },

      // UI state
      cartOpen: false,
      searchOpen: false,
      productModal: null,     // product id or null
      selectedVariant: null,  // variant id

      // Cart
      cart: JSON.parse(localStorage.getItem('cart') || '[]'),
      coupon: null,

      // Checkout
      checkoutStep: 1,
      checkout: {
        email: '', firstName: '', lastName: '',
        address: '', city: '', state: '', zip: '',
        cardNumber: '', cardExp: '', cardCvc: ''
      },

      // Orders
      lastOrder: null,

      // Toasts
      toasts: []
    };
    document.documentElement.setAttribute('data-theme', this.state.theme);
  }

  subscribe(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit() { this.persist(); this.listeners.forEach(fn => fn(this.state)); }

  persist() {
    localStorage.setItem('cart', JSON.stringify(this.state.cart));
    localStorage.setItem('theme', this.state.theme);
  }

  // Navigation
  go(view) { this.state.view = view; this.state.cartOpen = false; this.state.searchOpen = false; this.state.productModal = null; window.scrollTo({ top: 0, behavior: 'smooth' }); this.emit(); }

  // Theme
  toggleTheme() {
    this.state.theme = this.state.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', this.state.theme);
    this.emit();
  }

  // UI toggles
  openCart() { this.state.cartOpen = true; this.emit(); }
  closeCart() { this.state.cartOpen = false; this.emit(); }
  openSearch() { this.state.searchOpen = true; this.state.filter.search = ''; this.emit(); }
  closeSearch() { this.state.searchOpen = false; this.emit(); }

  openProduct(id) { this.state.productModal = id; const p = PRODUCTS.find(x => x.id === id); this.state.selectedVariant = p?.variants[0]?.id || null; this.emit(); }
  closeProduct() { this.state.productModal = null; this.state.selectedVariant = null; this.emit(); }
  selectVariant(vId) { this.state.selectedVariant = vId; this.emit(); }

  // Filters
  setFilter(key, val) { this.state.filter[key] = val; this.emit(); }

  // Cart
  addToCart(product, variantId) {
    const variant = product.variants.find(v => v.id === variantId) || product.variants[0];
    const key = `${product.id}__${variant.id}`;
    const existing = this.state.cart.find(i => i.key === key);
    if (existing) { existing.qty += 1; }
    else {
      this.state.cart.push({
        key, productId: product.id, variantId: variant.id,
        name: product.name, variantLabel: variant.label,
        image: product.images[0],
        price: product.price + variant.priceOffset,
        qty: 1
      });
    }
    this.toast(`${product.name} added to cart`);
    this.state.cartOpen = true;
    this.emit();
  }

  updateQty(key, delta) {
    const item = this.state.cart.find(i => i.key === key);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) this.state.cart = this.state.cart.filter(i => i.key !== key);
    this.emit();
  }

  removeItem(key) {
    this.state.cart = this.state.cart.filter(i => i.key !== key);
    this.emit();
  }

  applyCoupon(code) {
    const coupon = this.state.coupons.find(c => c.code.toUpperCase() === code.trim().toUpperCase());
    if (!coupon) { this.toast('Invalid coupon code', 'error'); return; }
    this.state.coupon = coupon;
    this.toast(`Coupon ${coupon.code} applied`);
    this.emit();
  }

  getCartTotals() {
    const subtotal = this.state.cart.reduce((s, i) => s + i.price * i.qty, 0);
    let discount = 0;
    if (this.state.coupon && subtotal >= this.state.coupon.minOrder) {
      discount = this.state.coupon.type === 'PERCENTAGE'
        ? subtotal * (this.state.coupon.value / 100)
        : this.state.coupon.value;
    }
    const shipping = subtotal >= 200 ? 0 : 9.99;
    const tax = Math.round((subtotal - discount) * 0.0825 * 100) / 100;
    const total = Math.max(0, subtotal - discount + shipping + tax);
    return { subtotal, discount, shipping, tax, total, itemCount: this.state.cart.reduce((s, i) => s + i.qty, 0) };
  }

  // Checkout
  setCheckoutField(key, val) { this.state.checkout[key] = val; this.emit(); }
  setCheckoutStep(n) { this.state.checkoutStep = n; this.emit(); }

  placeOrder() {
    const totals = this.getCartTotals();
    this.state.lastOrder = {
      id: `ORD-${Date.now().toString(36).toUpperCase()}`,
      date: new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
      items: [...this.state.cart],
      ...totals,
      shipping: this.state.checkout
    };
    this.state.cart = [];
    this.state.coupon = null;
    this.state.checkoutStep = 1;
    this.state.view = 'confirmation';
    this.state.cartOpen = false;
    this.emit();
  }

  // Toasts
  toast(message, type = 'default') {
    const id = Date.now();
    this.state.toasts.push({ id, message, type });
    this.emit();
    setTimeout(() => { this.state.toasts = this.state.toasts.filter(t => t.id !== id); this.emit(); }, 3000);
  }
}

export const store = new Store();
