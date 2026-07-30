/**
 * POST /cart — Add an item to the shopping cart
 *
 * Request body:
 *   { "product_id": "macbook-pro-16", "variant_id": "mbp-sb-1tb", "quantity": 1 }
 *
 * Validates the product exists in DynamoDB, then stores/increments in Redis.
 * Cart TTL is refreshed to 7 days on every write.
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand } from "@aws-sdk/lib-dynamodb";
import { RedisClient } from '../_lib/redis.mjs';
import { success, error } from '../_lib/response.mjs';

const dbClient = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(dbClient);
const TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';
const REDIS_HOST = process.env.REDIS_HOST || 'localhost';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379', 10);
const CART_TTL_SECONDS = 7 * 24 * 60 * 60; // 7 days

export async function handler(event) {
  try {
    const sessionId = event.headers?.['x-session-id'] || event.headers?.['X-Session-Id'];
    if (!sessionId) return error(400, 'Missing X-Session-Id header');

    const body = JSON.parse(event.body || '{}');
    const { product_id, variant_id, quantity = 1 } = body;

    if (!product_id) return error(400, 'Missing product_id');

    // Validate product exists
    const { Item: product } = await ddb.send(new GetCommand({
      TableName: TABLE,
      Key: { product_id }
    }));

    if (!product) return error(404, `Product '${product_id}' not found`);

    // Find variant (default to first)
    const variant = (product.variants || []).find(v => v.id === variant_id)
                 || (product.variants || [])[0]
                 || { id: 'default', label: 'Default', priceOffset: 0 };

    const itemKey = `${product_id}__${variant.id}`;
    const redis = new RedisClient(REDIS_HOST, REDIS_PORT);
    const cartKey = `cart:${sessionId}`;

    // Check if item already in cart
    const existing = await redis.hget(cartKey, itemKey);
    let cartItem;

    if (existing) {
      cartItem = JSON.parse(existing);
      cartItem.qty += quantity;
    } else {
      cartItem = {
        key: itemKey,
        product_id: product.product_id,
        variant_id: variant.id,
        name: product.name,
        variant_label: variant.label,
        image: (product.images || [])[0] || '',
        price: product.price + (variant.priceOffset || 0),
        qty: quantity
      };
    }

    await redis.hset(cartKey, itemKey, JSON.stringify(cartItem));
    await redis.expire(cartKey, CART_TTL_SECONDS);

    return success(200, { message: 'Item added to cart', item: cartItem });
  } catch (err) {
    console.error('Error adding to cart:', err);
    return error(500, 'Failed to add item to cart');
  }
}
