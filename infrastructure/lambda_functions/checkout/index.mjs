/**
 * POST /checkout — Process a checkout
 *
 * Flow:
 *   1. Validate cart is not empty (from Redis)
 *   2. Validate inventory for each item (DynamoDB)
 *   3. Simulate payment processing
 *   4. Create order in DynamoDB
 *   5. Publish order event to SQS for background processing
 *   6. Clear the shopping cart in Redis
 *   7. Return order confirmation
 *
 * Request body:
 *   {
 *     "email": "customer@example.com",
 *     "shipping": { "firstName": "...", "lastName": "...", "address": "...", ... },
 *     "payment": { "cardNumber": "4242...", "cardExp": "12/28", "cardCvc": "123" }
 *   }
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand, PutCommand } from "@aws-sdk/lib-dynamodb";
import { SQSClient, SendMessageCommand } from "@aws-sdk/client-sqs";
import { RedisClient } from '../_lib/redis.mjs';
import { success, error } from '../_lib/response.mjs';

const dbClient = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(dbClient);
const sqs = new SQSClient({ region: process.env.AWS_REGION || 'us-west-1' });

const PRODUCTS_TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';
const ORDERS_TABLE = process.env.ORDERS_TABLE || 'ecommerce-orders';
const ORDER_QUEUE_URL = process.env.ORDER_QUEUE_URL || '';
const REDIS_HOST = process.env.REDIS_HOST || 'localhost';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379', 10);

export async function handler(event) {
  try {
    const sessionId = event.headers?.['x-session-id'] || event.headers?.['X-Session-Id'];
    if (!sessionId) return error(400, 'Missing X-Session-Id header');

    const body = JSON.parse(event.body || '{}');
    const { email, shipping, payment } = body;

    if (!email) return error(400, 'Missing email');
    if (!shipping) return error(400, 'Missing shipping information');
    if (!payment) return error(400, 'Missing payment information');

    // ── Step 1: Retrieve cart from Redis ─────────────────────────
    const redis = new RedisClient(REDIS_HOST, REDIS_PORT);
    const cartKey = `cart:${sessionId}`;
    const cartData = await redis.hgetall(cartKey);
    const cartItems = Object.values(cartData).map(v => {
      try { return JSON.parse(v); } catch { return null; }
    }).filter(Boolean);

    if (cartItems.length === 0) {
      return error(400, 'Cart is empty');
    }

    // ── Step 2: Validate inventory ──────────────────────────────
    for (const item of cartItems) {
      const { Item: product } = await ddb.send(new GetCommand({
        TableName: PRODUCTS_TABLE,
        Key: { product_id: item.product_id }
      }));

      if (!product) {
        return error(400, `Product '${item.name}' is no longer available`);
      }
      if (product.stock_count !== undefined && product.stock_count < item.qty) {
        return error(400, `Insufficient stock for '${item.name}' (available: ${product.stock_count})`);
      }
    }

    // ── Step 3: Simulate payment ────────────────────────────────
    const paymentResult = simulatePayment(payment);
    if (!paymentResult.success) {
      return error(400, `Payment failed: ${paymentResult.reason}`);
    }

    // ── Step 4: Create order ────────────────────────────────────
    const subtotal = cartItems.reduce((sum, i) => sum + i.price * i.qty, 0);
    const shippingCost = subtotal >= 200 ? 0 : 9.99;
    const tax = Math.round(subtotal * 0.0825 * 100) / 100;
    const total = Math.round((subtotal + shippingCost + tax) * 100) / 100;

    const orderId = `ORD-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
    const now = new Date().toISOString();

    const order = {
      order_id: orderId,
      customer_email: email,
      status: 'confirmed',
      created_at: now,
      updated_at: now,
      items: cartItems,
      shipping: {
        ...shipping,
        method: 'standard',
        cost: shippingCost
      },
      payment: {
        method: 'card',
        last_four: (payment.cardNumber || '').slice(-4),
        transaction_id: paymentResult.transactionId
      },
      subtotal,
      tax,
      shipping_cost: shippingCost,
      total,
      item_count: cartItems.reduce((sum, i) => sum + i.qty, 0)
    };

    await ddb.send(new PutCommand({
      TableName: ORDERS_TABLE,
      Item: order
    }));

    // ── Step 5: Publish to SQS for background processing ───────
    if (ORDER_QUEUE_URL) {
      await sqs.send(new SendMessageCommand({
        QueueUrl: ORDER_QUEUE_URL,
        MessageBody: JSON.stringify({
          event_type: 'order_created',
          order_id: orderId,
          customer_email: email,
          items: cartItems,
          total,
          timestamp: now
        }),
        MessageGroupId: undefined // Standard queue, no group ID needed
      }));
    }

    // ── Step 6: Clear cart ──────────────────────────────────────
    await redis.del(cartKey);

    // ── Step 7: Return confirmation ─────────────────────────────
    return success(200, {
      message: 'Order placed successfully',
      order: {
        order_id: orderId,
        status: 'confirmed',
        total,
        item_count: order.item_count,
        created_at: now
      }
    });
  } catch (err) {
    console.error('Checkout error:', err);
    return error(500, 'Checkout failed');
  }
}

/**
 * Simulate payment processing.
 * In production, this would integrate with Stripe, Square, etc.
 */
function simulatePayment(payment) {
  // Simulate basic validation
  const cardNumber = (payment.cardNumber || '').replace(/\s/g, '');
  if (cardNumber.length < 13 || cardNumber.length > 19) {
    return { success: false, reason: 'Invalid card number' };
  }

  // Simulate a ~2% random failure rate for realism
  if (Math.random() < 0.02) {
    return { success: false, reason: 'Card declined by issuer' };
  }

  return {
    success: true,
    transactionId: `TXN-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`
  };
}
