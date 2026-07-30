/**
 * PUT /cart — Update item quantity in the shopping cart
 *
 * Request body:
 *   { "item_key": "macbook-pro-16__mbp-sb-1tb", "quantity": 3 }
 *
 * Sets the absolute quantity. If quantity <= 0, removes the item.
 */

import { RedisClient } from '../_lib/redis.mjs';
import { success, error } from '../_lib/response.mjs';

const REDIS_HOST = process.env.REDIS_HOST || 'localhost';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379', 10);
const CART_TTL_SECONDS = 7 * 24 * 60 * 60;

export async function handler(event) {
  try {
    const sessionId = event.headers?.['x-session-id'] || event.headers?.['X-Session-Id'];
    if (!sessionId) return error(400, 'Missing X-Session-Id header');

    const body = JSON.parse(event.body || '{}');
    const { item_key, quantity } = body;

    if (!item_key) return error(400, 'Missing item_key');
    if (quantity === undefined) return error(400, 'Missing quantity');

    const redis = new RedisClient(REDIS_HOST, REDIS_PORT);
    const cartKey = `cart:${sessionId}`;

    if (quantity <= 0) {
      // Remove item
      await redis.hdel(cartKey, item_key);
      return success(200, { message: 'Item removed from cart' });
    }

    // Get existing item to update quantity
    const existing = await redis.hget(cartKey, item_key);
    if (!existing) return error(404, 'Item not found in cart');

    const cartItem = JSON.parse(existing);
    cartItem.qty = quantity;

    await redis.hset(cartKey, item_key, JSON.stringify(cartItem));
    await redis.expire(cartKey, CART_TTL_SECONDS);

    return success(200, { message: 'Cart updated', item: cartItem });
  } catch (err) {
    console.error('Error updating cart:', err);
    return error(500, 'Failed to update cart');
  }
}
