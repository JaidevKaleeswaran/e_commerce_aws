/**
 * Shared Response Helpers
 * Provides consistent CORS headers and response formatting across all Lambda handlers.
 */

const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type,X-Session-Id'
};

/**
 * Build a successful JSON response.
 * @param {number} statusCode - HTTP status code
 * @param {any} body - Response payload (will be JSON-stringified)
 */
export function success(statusCode, body) {
  return {
    statusCode,
    headers: CORS_HEADERS,
    body: JSON.stringify(body)
  };
}

/**
 * Build an error JSON response.
 * @param {number} statusCode - HTTP status code
 * @param {string} message - Human-readable error message
 */
export function error(statusCode, message) {
  return {
    statusCode,
    headers: CORS_HEADERS,
    body: JSON.stringify({ error: message })
  };
}

/**
 * Handle CORS preflight OPTIONS requests.
 */
export function options() {
  return { statusCode: 200, headers: CORS_HEADERS, body: '' };
}
