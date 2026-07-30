/**
 * GET /categories — Return distinct product categories
 *
 * Scans the products table and extracts unique categories.
 * For a small catalog this is efficient; for large catalogs,
 * consider a dedicated categories table.
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand } from "@aws-sdk/lib-dynamodb";
import { success, error } from '../_lib/response.mjs';

const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(client);
const TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';

export async function handler(event) {
  try {
    // Projection scan — only fetch the category field to minimize read cost
    const { Items } = await ddb.send(new ScanCommand({
      TableName: TABLE,
      ProjectionExpression: 'category'
    }));

    // Deduplicate and count
    const counts = {};
    for (const item of Items) {
      const cat = item.category;
      counts[cat] = (counts[cat] || 0) + 1;
    }

    const categories = Object.entries(counts).map(([id, count]) => ({
      id,
      name: id.charAt(0).toUpperCase() + id.slice(1),
      count
    }));

    return success(200, categories);
  } catch (err) {
    console.error('Error fetching categories:', err);
    return error(500, 'Failed to fetch categories');
  }
}
