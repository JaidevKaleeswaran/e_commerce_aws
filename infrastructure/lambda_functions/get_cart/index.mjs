/**
 * GET /cart — Retrieve the shopping cart for a session
 *
 * Uses the X-Session-Id header (or query param ?session_id) to identify the cart.
 * Cart data is stored in Redis as a hash: cart:{sessionId} → { itemKey: JSON }
 */

import { RedisClient } from '../_lib/redis.mjs';
import { success, error } from '../_lib/response.mjs';

const REDIS_HOST = process.env.REDIS_HOST || 'localhost';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379', 10);

export async function handler(event) {
  try {
    const sessionId = event.headers?.['x-session-id'] ||
                      event.headers?.['X-Session-Id'] ||
                      event.queryStringParameters?.session_id;

    if (!sessionId) {
      return error(400, 'Missing X-Session-Id header or session_id parameter');
    }

    const redis = new RedisClient(REDIS_HOST, REDIS_PORT);
    const cartKey = `cart:${sessionId}`;
    const cartData = await redis.hgetall(cartKey);

    // Parse each field value from JSON
    const items = Object.values(cartData).map(val => {
      try { return JSON.parse(val); } catch { return null; }
    }).filter(Boolean);

    return success(200, { session_id: sessionId, items });
  } catch (err) {
    console.error('Error fetching cart:', err);
    return error(500, 'Failed to retrieve cart');
  }
}
