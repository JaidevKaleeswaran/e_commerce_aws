/**
 * Mock Database — Curated product catalog
 */

export const CATEGORIES = [
  { id: 'laptops', name: 'Laptops', count: 3 },
  { id: 'audio', name: 'Audio', count: 2 },
  { id: 'wearables', name: 'Wearables', count: 1 },
  { id: 'accessories', name: 'Accessories', count: 2 }
];

export const PRODUCTS = [
  {
    id: 'macbook-pro-16',
    name: 'MacBook Pro 16"',
    subtitle: 'M3 Max · 48GB · 1TB',
    category: 'laptops',
    price: 3499,
    rating: 4.9,
    reviews: 128,
    inStock: true,
    stockCount: 23,
    badge: 'New',
    description: 'The most powerful MacBook Pro ever. Built for professionals who push the limits of creativity and productivity.',
    specs: { Chip: 'Apple M3 Max', Memory: '48GB Unified', Storage: '1TB SSD', Display: '16.2" Liquid Retina XDR', Battery: 'Up to 22 hours' },
    images: [
      'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=800&q=80',
      'https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'mbp-sb-1tb', label: 'Space Black · 1TB', priceOffset: 0 },
      { id: 'mbp-sb-2tb', label: 'Space Black · 2TB', priceOffset: 400 },
      { id: 'mbp-sl-1tb', label: 'Silver · 1TB', priceOffset: 0 }
    ]
  },
  {
    id: 'macbook-air-15',
    name: 'MacBook Air 15"',
    subtitle: 'M3 · 24GB · 512GB',
    category: 'laptops',
    price: 1699,
    rating: 4.8,
    reviews: 94,
    inStock: true,
    stockCount: 45,
    badge: null,
    description: 'Strikingly thin design with the power of the M3 chip. The world\'s best consumer laptop.',
    specs: { Chip: 'Apple M3', Memory: '24GB Unified', Storage: '512GB SSD', Display: '15.3" Liquid Retina', Battery: 'Up to 18 hours' },
    images: [
      'https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'mba-mid-512', label: 'Midnight · 512GB', priceOffset: 0 },
      { id: 'mba-star-1tb', label: 'Starlight · 1TB', priceOffset: 200 }
    ]
  },
  {
    id: 'studio-display',
    name: 'Studio Display',
    subtitle: '27" 5K Retina',
    category: 'laptops',
    price: 1599,
    rating: 4.7,
    reviews: 56,
    inStock: true,
    stockCount: 18,
    badge: null,
    description: 'A stunning 27-inch 5K Retina display with 600 nits of brightness, P3 wide color, and a 12MP camera with Center Stage.',
    specs: { Resolution: '5120 x 2880', Brightness: '600 nits', Camera: '12MP Ultra Wide', Audio: 'Six-speaker system' },
    images: [
      'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'sd-standard', label: 'Standard Glass', priceOffset: 0 },
      { id: 'sd-nano', label: 'Nano-texture Glass', priceOffset: 300 }
    ]
  },
  {
    id: 'airpods-max',
    name: 'AirPods Max',
    subtitle: 'Wireless Over-Ear',
    category: 'audio',
    price: 549,
    rating: 4.8,
    reviews: 212,
    inStock: true,
    stockCount: 67,
    badge: null,
    description: 'High-fidelity audio with Active Noise Cancellation. Computational audio creates an immersive listening experience.',
    specs: { Driver: '40mm Apple-designed', ANC: 'Active Noise Cancellation', Battery: '20 hours', Connectivity: 'Bluetooth 5.0' },
    images: [
      'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'apm-silver', label: 'Silver', priceOffset: 0 },
      { id: 'apm-midnight', label: 'Midnight', priceOffset: 0 }
    ]
  },
  {
    id: 'homepod',
    name: 'HomePod',
    subtitle: 'Smart Speaker',
    category: 'audio',
    price: 299,
    rating: 4.6,
    reviews: 73,
    inStock: true,
    stockCount: 34,
    badge: null,
    description: 'Room-filling, immersive sound. Siri intelligence. Smart home capabilities. A great experience at every level.',
    specs: { Woofer: 'High-excursion', Tweeters: 'Five beamforming', Spatial: 'Dolby Atmos', Assistant: 'Siri built-in' },
    images: [
      'https://images.unsplash.com/photo-1558089687-f282ffcbc126?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'hp-white', label: 'White', priceOffset: 0 },
      { id: 'hp-midnight', label: 'Midnight', priceOffset: 0 }
    ]
  },
  {
    id: 'apple-watch-ultra',
    name: 'Watch Ultra 2',
    subtitle: 'Titanium · 49mm',
    category: 'wearables',
    price: 799,
    rating: 4.9,
    reviews: 89,
    inStock: true,
    stockCount: 15,
    badge: 'New',
    description: 'The most rugged and capable Apple Watch. Precision dual-frequency GPS. Up to 36 hours of battery life.',
    specs: { Case: 'Grade 5 Titanium', Display: '3000 nits OLED', Water: '100m certified', Sensors: 'ECG, SpO2, Temperature' },
    images: [
      'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'awu-natural', label: 'Natural Titanium', priceOffset: 0 },
      { id: 'awu-black', label: 'Black Titanium', priceOffset: 50 }
    ]
  },
  {
    id: 'magic-keyboard',
    name: 'Magic Keyboard',
    subtitle: 'With Touch ID',
    category: 'accessories',
    price: 199,
    rating: 4.7,
    reviews: 148,
    inStock: true,
    stockCount: 92,
    badge: null,
    description: 'Wireless keyboard with a remarkably comfortable typing experience, Touch ID, and a built-in rechargeable battery.',
    specs: { Connection: 'Bluetooth / Lightning', Layout: 'Full-size with numpad', Auth: 'Touch ID', Battery: 'Rechargeable' },
    images: [
      'https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'mk-silver', label: 'Silver', priceOffset: 0 },
      { id: 'mk-black', label: 'Black', priceOffset: 30 }
    ]
  },
  {
    id: 'magic-mouse',
    name: 'Magic Mouse',
    subtitle: 'Multi-Touch Surface',
    category: 'accessories',
    price: 99,
    rating: 4.5,
    reviews: 203,
    inStock: true,
    stockCount: 110,
    badge: null,
    description: 'Wireless and rechargeable, with an optimized foot design that lets it glide effortlessly across your desk.',
    specs: { Surface: 'Multi-Touch', Connection: 'Bluetooth', Battery: 'Built-in rechargeable', Tracking: 'Laser' },
    images: [
      'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=800&q=80'
    ],
    variants: [
      { id: 'mm-white', label: 'White', priceOffset: 0 },
      { id: 'mm-black', label: 'Black', priceOffset: 30 }
    ]
  }
];

export const COUPONS = [
  { code: 'WELCOME10', type: 'PERCENTAGE', value: 10, minOrder: 100 },
  { code: 'SAVE50', type: 'FIXED', value: 50, minOrder: 500 }
];
