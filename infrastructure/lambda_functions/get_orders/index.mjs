/**
 * GET /orders          — List orders for a customer (by email)
 * GET /orders/{id}     — Get a single order by ID
 *
 * Query params for list:
 *   ?email=customer@example.com   — Required for listing orders
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { success, error } from '../_lib/response.mjs';

const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(client);
const TABLE = process.env.ORDERS_TABLE || 'ecommerce-orders';

export async function handler(event) {
  try {
    const orderId = event.pathParameters?.id;

    if (orderId) {
      // ── Single order by ID ────────────────────────────────────
      const { Item } = await ddb.send(new GetCommand({
        TableName: TABLE,
        Key: { order_id: orderId }
      }));

      if (!Item) return error(404, `Order '${orderId}' not found`);

      return success(200, Item);
    }

    // ── List orders by customer email ───────────────────────────
    const email = event.queryStringParameters?.email;
    if (!email) return error(400, 'Missing email parameter');

    const { Items } = await ddb.send(new QueryCommand({
      TableName: TABLE,
      IndexName: 'customer-email-index',
      KeyConditionExpression: 'customer_email = :email',
      ExpressionAttributeValues: { ':email': email },
      ScanIndexForward: false  // Most recent first
    }));

    return success(200, Items || []);
  } catch (err) {
    console.error('Error fetching orders:', err);
    return error(500, 'Failed to fetch orders');
  }
}
