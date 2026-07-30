/**
 * SNS-triggered Lambda — Send order confirmation email
 *
 * Listens to the order-events SNS topic and sends a confirmation
 * email via SES when an order_completed event is received.
 *
 * This is a secondary notification pathway — the primary email is sent
 * by process_order. This handler can be extended for additional
 * notification channels (SMS, push, webhooks).
 */

import { SESClient, SendEmailCommand } from "@aws-sdk/client-ses";

const ses = new SESClient({ region: process.env.AWS_REGION || 'us-west-1' });
const SES_SENDER_EMAIL = process.env.SES_SENDER_EMAIL || '';

export async function handler(event) {
  for (const record of event.Records) {
    try {
      const snsMessage = JSON.parse(record.Sns.Message);
      console.log(`Received SNS event: ${snsMessage.event_type} for order ${snsMessage.order_id}`);

      // Only process order_completed events
      if (snsMessage.event_type !== 'order_completed') {
        console.log(`Skipping event type: ${snsMessage.event_type}`);
        continue;
      }

      if (!SES_SENDER_EMAIL || !snsMessage.customer_email) {
        console.log('SES not configured or no customer email, skipping');
        continue;
      }

      // Send a lightweight receipt email
      await ses.send(new SendEmailCommand({
        Source: SES_SENDER_EMAIL,
        Destination: { ToAddresses: [snsMessage.customer_email] },
        Message: {
          Subject: { Data: `Your Receipt — ${snsMessage.order_id}` },
          Body: {
            Html: {
              Data: `
                <div style="max-width:600px;margin:0 auto;font-family:system-ui,-apple-system,sans-serif;color:#1a1a1a">
                  <div style="padding:32px 24px;text-align:center">
                    <h2 style="margin:0 0 16px">Purchase Receipt</h2>
                    <p style="color:#666">Order: ${snsMessage.order_id}</p>
                    <p style="font-size:28px;font-weight:700;margin:16px 0">$${(snsMessage.total || 0).toFixed(2)}</p>
                    <p style="color:#666;font-size:14px">${snsMessage.timestamp || new Date().toISOString()}</p>
                  </div>
                  <div style="padding:16px 24px;text-align:center;color:#999;font-size:13px;border-top:1px solid #eee">
                    <p>Thank you for shopping with AURA.</p>
                  </div>
                </div>`
            }
          }
        }
      }));

      console.log(`Receipt email sent for order ${snsMessage.order_id}`);
    } catch (err) {
      console.error('Send confirmation failed:', err);
      // Don't throw — SNS doesn't retry like SQS. Log and move on.
    }
  }
}
