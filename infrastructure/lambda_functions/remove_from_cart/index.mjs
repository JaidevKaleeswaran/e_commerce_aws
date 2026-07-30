/**
 * DELETE /cart — Remove an item from the shopping cart
 *
 * Query params:
 *   ?item_key=macbook-pro-16__mbp-sb-1tb
 *
 * Or request body:
 *   { "item_key": "macbook-pro-16__mbp-sb-1tb" }
 */

import { RedisClient } from '../_lib/redis.mjs';
import { success, error } from '../_lib/response.mjs';

const REDIS_HOST = process.env.REDIS_HOST || 'localhost';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379', 10);

export async function handler(event) {
  try {
    const sessionId = event.headers?.['x-session-id'] || event.headers?.['X-Session-Id'];
    if (!sessionId) return error(400, 'Missing X-Session-Id header');

    // Accept item_key from query string or body
    const itemKey = event.queryStringParameters?.item_key ||
                    JSON.parse(event.body || '{}').item_key;

    if (!itemKey) return error(400, 'Missing item_key');

    const redis = new RedisClient(REDIS_HOST, REDIS_PORT);
    const cartKey = `cart:${sessionId}`;

    await redis.hdel(cartKey, itemKey);

    return success(200, { message: 'Item removed from cart' });
  } catch (err) {
    console.error('Error removing from cart:', err);
    return error(500, 'Failed to remove item from cart');
  }
}
