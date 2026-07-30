/**
 * Lightweight Redis Client
 * Uses Node's built-in `net` module to speak the RESP protocol directly.
 * No npm dependencies required — deploys as a single file in Lambda.
 *
 * Supports: GET, SET, DEL, HGETALL, HSET, HDEL, EXPIRE, EXISTS
 */

import net from 'net';

export class RedisClient {
  constructor(host, port = 6379, timeoutMs = 5000) {
    this.host = host;
    this.port = port;
    this.timeoutMs = timeoutMs;
  }

  /**
   * Execute a single Redis command.
   * @param  {...string} args - Command and arguments, e.g. ('HSET', 'key', 'field', 'value')
   * @returns {Promise<any>} Parsed RESP response
   */
  exec(...args) {
    return new Promise((resolve, reject) => {
      const socket = net.createConnection({ host: this.host, port: this.port });
      const encoded = this._encode(args);
      let buffer = Buffer.alloc(0);

      const timer = setTimeout(() => {
        socket.destroy();
        reject(new Error('Redis command timed out'));
      }, this.timeoutMs);

      socket.on('connect', () => socket.write(encoded));
      socket.on('data', (chunk) => {
        buffer = Buffer.concat([buffer, chunk]);
        // Try to parse — if we have a complete response, resolve
        try {
          const [result] = this._decode(buffer.toString(), 0);
          clearTimeout(timer);
          socket.end();
          resolve(result);
        } catch (_) {
          // Incomplete response, wait for more data
        }
      });
      socket.on('error', (err) => { clearTimeout(timer); reject(err); });
      socket.on('close', () => clearTimeout(timer));
    });
  }

  // ── RESP Encoder ──────────────────────────────────────────────

  _encode(args) {
    let out = `*${args.length}\r\n`;
    for (const arg of args) {
      const str = String(arg);
      out += `$${Buffer.byteLength(str)}\r\n${str}\r\n`;
    }
    return out;
  }

  // ── RESP Decoder ──────────────────────────────────────────────

  _decode(data, pos) {
    const type = data[pos];
    const nextCrlf = data.indexOf('\r\n', pos);
    if (nextCrlf === -1) throw new Error('incomplete');

    switch (type) {
      case '+': // Simple string
        return [data.slice(pos + 1, nextCrlf), nextCrlf + 2];

      case '-': // Error
        throw new Error(data.slice(pos + 1, nextCrlf));

      case ':': // Integer
        return [parseInt(data.slice(pos + 1, nextCrlf), 10), nextCrlf + 2];

      case '$': { // Bulk string
        const len = parseInt(data.slice(pos + 1, nextCrlf), 10);
        if (len === -1) return [null, nextCrlf + 2];
        const start = nextCrlf + 2;
        const end = start + len;
        if (data.length < end + 2) throw new Error('incomplete');
        return [data.slice(start, end), end + 2];
      }

      case '*': { // Array
        const count = parseInt(data.slice(pos + 1, nextCrlf), 10);
        if (count === -1) return [null, nextCrlf + 2];
        const result = [];
        let cursor = nextCrlf + 2;
        for (let i = 0; i < count; i++) {
          const [val, next] = this._decode(data, cursor);
          result.push(val);
          cursor = next;
        }
        return [result, cursor];
      }

      default:
        throw new Error(`Unknown RESP type: ${type}`);
    }
  }

  // ── Convenience Methods ───────────────────────────────────────

  async hset(key, field, value) { return this.exec('HSET', key, field, value); }
  async hget(key, field) { return this.exec('HGET', key, field); }
  async hdel(key, field) { return this.exec('HDEL', key, field); }
  async del(key) { return this.exec('DEL', key); }
  async expire(key, seconds) { return this.exec('EXPIRE', key, seconds); }
  async exists(key) { return this.exec('EXISTS', key); }

  async hgetall(key) {
    const arr = await this.exec('HGETALL', key);
    if (!arr || !Array.isArray(arr)) return {};
    const obj = {};
    for (let i = 0; i < arr.length; i += 2) {
      obj[arr[i]] = arr[i + 1];
    }
    return obj;
  }
}
