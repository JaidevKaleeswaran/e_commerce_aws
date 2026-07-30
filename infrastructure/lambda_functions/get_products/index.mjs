/**
 * GET /products — List products with optional category/featured filters
 *
 * Query params:
 *   ?category=laptops    — Filter by category (uses category-index GSI)
 *   ?featured=true       — Return featured/new products (uses badge-index GSI)
 *   (no params)          — Return all products
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { success, error } from '../_lib/response.mjs';

const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(client);
const TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';

export async function handler(event) {
  try {
    const params = event.queryStringParameters || {};
    const category = params.category;
    const featured = params.featured;
    let items;

    if (category && category !== 'all') {
      // Query by category using GSI
      const result = await ddb.send(new QueryCommand({
        TableName: TABLE,
        IndexName: 'category-index',
        KeyConditionExpression: 'category = :cat',
        ExpressionAttributeValues: { ':cat': category }
      }));
      items = result.Items;
    } else if (featured === 'true') {
      // Query featured products using badge GSI
      const result = await ddb.send(new QueryCommand({
        TableName: TABLE,
        IndexName: 'badge-index',
        KeyConditionExpression: 'badge = :badge',
        ExpressionAttributeValues: { ':badge': 'New' }
      }));
      items = result.Items;
    } else {
      // Full scan — acceptable for small catalogs
      const result = await ddb.send(new ScanCommand({ TableName: TABLE }));
      items = result.Items;
    }

    return success(200, items);
  } catch (err) {
    console.error('Error fetching products:', err);
    return error(500, 'Failed to fetch products');
  }
}
