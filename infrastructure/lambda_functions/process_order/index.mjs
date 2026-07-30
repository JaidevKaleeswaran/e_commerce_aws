/**
 * SQS-triggered Lambda — Background order processing
 *
 * Triggered when an order event is published to the order-processing queue.
 * Responsibilities:
 *   1. Update product inventory (decrement stock_count)
 *   2. Update order status to 'processing' → 'completed'
 *   3. Publish SNS notification for downstream consumers
 *   4. Trigger confirmation email via SNS
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { SNSClient, PublishCommand } from "@aws-sdk/client-sns";
import { SESClient, SendEmailCommand } from "@aws-sdk/client-ses";

const dbClient = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(dbClient);
const sns = new SNSClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ses = new SESClient({ region: process.env.AWS_REGION || 'us-west-1' });

const PRODUCTS_TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';
const ORDERS_TABLE = process.env.ORDERS_TABLE || 'ecommerce-orders';
const ORDER_EVENTS_TOPIC_ARN = process.env.ORDER_EVENTS_TOPIC_ARN || '';
const SES_SENDER_EMAIL = process.env.SES_SENDER_EMAIL || '';

export async function handler(event) {
  for (const record of event.Records) {
    try {
      const message = JSON.parse(record.body);
      console.log(`Processing order: ${message.order_id}`);

      // ── Step 1: Update order status to 'processing' ───────────
      await updateOrderStatus(message.order_id, 'processing');

      // ── Step 2: Decrement inventory for each item ─────────────
      for (const item of message.items || []) {
        try {
          await ddb.send(new UpdateCommand({
            TableName: PRODUCTS_TABLE,
            Key: { product_id: item.product_id },
            UpdateExpression: 'SET stock_count = stock_count - :qty, updated_at = :now',
            ExpressionAttributeValues: {
              ':qty': item.qty,
              ':now': new Date().toISOString()
            },
            ConditionExpression: 'stock_count >= :qty'
          }));
          console.log(`  Inventory updated: ${item.product_id} (-${item.qty})`);
        } catch (invErr) {
          console.error(`  Inventory update failed for ${item.product_id}:`, invErr.message);
          // Continue processing — don't fail the whole order for one item
        }
      }

      // ── Step 3: Update order status to 'completed' ────────────
      await updateOrderStatus(message.order_id, 'completed');

      // ── Step 4: Send confirmation email ───────────────────────
      if (SES_SENDER_EMAIL && message.customer_email) {
        try {
          await ses.send(new SendEmailCommand({
            Source: SES_SENDER_EMAIL,
            Destination: { ToAddresses: [message.customer_email] },
            Message: {
              Subject: { Data: `Order Confirmed: ${message.order_id}` },
              Body: {
                Html: {
                  Data: buildConfirmationEmail(message)
                }
              }
            }
          }));
          console.log(`  Confirmation email sent to ${message.customer_email}`);
        } catch (emailErr) {
          console.error('  Email send failed (SES sandbox?):', emailErr.message);
        }
      }

      // ── Step 5: Publish SNS event ─────────────────────────────
      if (ORDER_EVENTS_TOPIC_ARN) {
        await sns.send(new PublishCommand({
          TopicArn: ORDER_EVENTS_TOPIC_ARN,
          Subject: 'Order Completed',
          Message: JSON.stringify({
            event_type: 'order_completed',
            order_id: message.order_id,
            customer_email: message.customer_email,
            total: message.total,
            timestamp: new Date().toISOString()
          }),
          MessageAttributes: {
            event_type: { DataType: 'String', StringValue: 'order_completed' }
          }
        }));
        console.log(`  SNS event published for order ${message.order_id}`);
      }

      console.log(`Order ${message.order_id} processed successfully`);
    } catch (err) {
      console.error('Order processing failed:', err);
      throw err; // Let SQS retry (or move to DLQ after max retries)
    }
  }
}

async function updateOrderStatus(orderId, status) {
  await ddb.send(new UpdateCommand({
    TableName: ORDERS_TABLE,
    Key: { order_id: orderId },
    UpdateExpression: 'SET #s = :status, updated_at = :now',
    ExpressionAttributeNames: { '#s': 'status' },
    ExpressionAttributeValues: {
      ':status': status,
      ':now': new Date().toISOString()
    }
  }));
}

function buildConfirmationEmail(order) {
  const itemRows = (order.items || []).map(i =>
    `<tr><td style="padding:8px;border-bottom:1px solid #eee">${i.name}</td>
     <td style="padding:8px;border-bottom:1px solid #eee;text-align:center">${i.qty}</td>
     <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">$${(i.price * i.qty).toFixed(2)}</td></tr>`
  ).join('');

  return `
    <div style="max-width:600px;margin:0 auto;font-family:system-ui,-apple-system,sans-serif;color:#1a1a1a">
      <div style="padding:32px 24px;text-align:center;background:#f8f9fa">
        <h1 style="margin:0 0 8px;font-size:24px;font-weight:600">Order Confirmed ✓</h1>
        <p style="margin:0;color:#666">${order.order_id}</p>
      </div>
      <div style="padding:24px">
        <table style="width:100%;border-collapse:collapse">
          <thead><tr style="border-bottom:2px solid #1a1a1a">
            <th style="padding:8px;text-align:left">Item</th>
            <th style="padding:8px;text-align:center">Qty</th>
            <th style="padding:8px;text-align:right">Total</th>
          </tr></thead>
          <tbody>${itemRows}</tbody>
          <tfoot><tr>
            <td colspan="2" style="padding:12px 8px;font-weight:600">Total</td>
            <td style="padding:12px 8px;text-align:right;font-weight:600">$${(order.total || 0).toFixed(2)}</td>
          </tr></tfoot>
        </table>
      </div>
      <div style="padding:16px 24px;text-align:center;color:#999;font-size:13px">
        <p>Thank you for your purchase! You will receive shipping updates via email.</p>
      </div>
    </div>`;
}
