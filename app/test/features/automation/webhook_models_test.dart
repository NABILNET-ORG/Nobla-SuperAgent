import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/automation/models/webhook_models.dart';

void main() {
  group('WebhookDirection', () {
    test('fromString parses values', () {
      expect(WebhookDirection.fromString('inbound'), WebhookDirection.inbound);
      expect(WebhookDirection.fromString('outbound'), WebhookDirection.outbound);
      expect(WebhookDirection.fromString('x'), WebhookDirection.inbound);
    });
  });

  group('WebhookHealthStatus', () {
    test('fromString parses values', () {
      expect(WebhookHealthStatus.fromString('healthy'),
          WebhookHealthStatus.healthy);
      expect(WebhookHealthStatus.fromString('degraded'),
          WebhookHealthStatus.degraded);
      expect(WebhookHealthStatus.fromString('failing'),
          WebhookHealthStatus.failing);
    });

    test('label returns capitalized', () {
      expect(WebhookHealthStatus.healthy.label, 'Healthy');
    });
  });

  group('WebhookEntry', () {
    test('fromJson parses all fields', () {
      final wh = WebhookEntry.fromJson({
        'webhook_id': 'wh1',
        'name': 'GitHub Push',
        'direction': 'inbound',
        'url': 'https://example.com',
        'event_type_prefix': 'github.push',
        'signature_scheme': 'hmac-sha256',
        'status': 'active',
        'created_at': '2026-03-28T10:00:00',
      });
      expect(wh.webhookId, 'wh1');
      expect(wh.name, 'GitHub Push');
      expect(wh.direction, WebhookDirection.inbound);
      expect(wh.eventTypePrefix, 'github.push');
      expect(wh.isActive, true);
    });

    test('fromJson handles defaults', () {
      final wh = WebhookEntry.fromJson({});
      expect(wh.direction, WebhookDirection.inbound);
      expect(wh.signatureScheme, 'hmac-sha256');
      expect(wh.status, 'active');
    });

    test('isActive reflects status', () {
      final active = WebhookEntry.fromJson({'status': 'active'});
      final paused = WebhookEntry.fromJson({'status': 'paused'});
      expect(active.isActive, true);
      expect(paused.isActive, false);
    });
  });

  group('WebhookHealth', () {
    test('fromJson parses all fields', () {
      final h = WebhookHealth.fromJson({
        'webhook_id': 'wh1',
        'event_count': 100,
        'failure_count': 5,
        'failure_rate': 0.05,
        'dead_letter_count': 2,
        'last_received_at': '2026-03-28T10:00:00',
        'status': 'healthy',
      });
      expect(h.eventCount, 100);
      expect(h.failureRate, 0.05);
      expect(h.deadLetterCount, 2);
      expect(h.status, WebhookHealthStatus.healthy);
    });

    test('fromJson handles missing optional', () {
      final h = WebhookHealth.fromJson({});
      expect(h.lastReceivedAt, null);
      expect(h.eventCount, 0);
    });
  });

  group('WebhookEvent', () {
    test('fromJson parses all fields', () {
      final e = WebhookEvent.fromJson({
        'event_id': 'ev1',
        'webhook_id': 'wh1',
        'signature_valid': true,
        'status': 'processed',
        'retry_count': 0,
        'created_at': '2026-03-28T10:00:00',
      });
      expect(e.eventId, 'ev1');
      expect(e.signatureValid, true);
      expect(e.status, 'processed');
    });

    test('fromJson handles defaults', () {
      final e = WebhookEvent.fromJson({});
      expect(e.signatureValid, false);
      expect(e.retryCount, 0);
    });
  });
}
