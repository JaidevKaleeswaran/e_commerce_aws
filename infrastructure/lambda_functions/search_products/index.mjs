/**
 * GET /search?q=keyword — Full-text product search
 *
 * Uses OpenSearch when available, falls back to DynamoDB scan with
 * client-side filtering when OpenSearch is not configured.
 *
 * Query params:
 *   ?q=macbook          — Search query (name, description, category)
 *   ?category=laptops   — Optional category filter
 */

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand } from "@aws-sdk/lib-dynamodb";
import { success, error } from '../_lib/response.mjs';
import https from 'https';

const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-west-1' });
const ddb = DynamoDBDocumentClient.from(client);
const TABLE = process.env.PRODUCTS_TABLE || 'ecommerce-products';
const OPENSEARCH_ENDPOINT = process.env.OPENSEARCH_ENDPOINT || '';

export async function handler(event) {
  try {
    const params = event.queryStringParameters || {};
    const query = (params.q || '').trim().toLowerCase();

    if (!query) {
      return error(400, 'Missing search query parameter "q"');
    }

    // Try OpenSearch first if configured
    if (OPENSEARCH_ENDPOINT) {
      try {
        const results = await searchOpenSearch(query, params.category);
        return success(200, results);
      } catch (osErr) {
        console.warn('OpenSearch unavailable, falling back to DynamoDB:', osErr.message);
      }
    }

    // Fallback: DynamoDB scan with client-side filtering
    const { Items } = await ddb.send(new ScanCommand({ TableName: TABLE }));

    const filtered = Items.filter(item => {
      const matchesQuery =
        (item.name || '').toLowerCase().includes(query) ||
        (item.description || '').toLowerCase().includes(query) ||
        (item.category || '').toLowerCase().includes(query) ||
        (item.subtitle || '').toLowerCase().includes(query);

      const matchesCategory = !params.category || params.category === 'all' ||
        item.category === params.category;

      return matchesQuery && matchesCategory;
    });

    return success(200, filtered);
  } catch (err) {
    console.error('Search error:', err);
    return error(500, 'Search failed');
  }
}

/**
 * Query OpenSearch for products matching the search term.
 */
function searchOpenSearch(query, category) {
  return new Promise((resolve, reject) => {
    const searchBody = {
      query: {
        bool: {
          must: [
            {
              multi_match: {
                query,
                fields: ['name^3', 'description', 'category^2', 'subtitle'],
                fuzziness: 'AUTO'
              }
            }
          ],
          ...(category && category !== 'all' ? {
            filter: [{ term: { 'category.keyword': category } }]
          } : {})
        }
      },
      size: 50
    };

    const postData = JSON.stringify(searchBody);
    const url = new URL(`https://${OPENSEARCH_ENDPOINT}/products/_search`);

    const req = https.request({
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData)
      }
    }, (res) => {
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(body);
          const hits = (parsed.hits?.hits || []).map(h => h._source);
          resolve(hits);
        } catch (e) {
          reject(new Error('Failed to parse OpenSearch response'));
        }
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}
