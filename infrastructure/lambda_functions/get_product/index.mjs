/**
 * GET /products/{id} — Retrieve a single product by ID
 *
 * Path param: id — The product_id to look up
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand } from "@aws-sdk/lib-dynamodb";
import { success, error } from '../_lib/response.mjs';

const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(client);
const TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';

export async function handler(event) {
  try {
    const productId = event.pathParameters?.id;
    if (!productId) {
      return error(400, 'Missing product ID');
    }

    const { Item } = await ddb.send(new GetCommand({
      TableName: TABLE,
      Key: { product_id: productId }
    }));

    if (!Item) {
      return error(404, `Product '${productId}' not found`);
    }

    return success(200, Item);
  } catch (err) {
    console.error('Error fetching product:', err);
    return error(500, 'Failed to fetch product');
  }
}
