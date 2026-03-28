import 'package:flutter/foundation.dart';

/// Webhook direction.
enum WebhookDirection {
  inbound,
  outbound;

  static WebhookDirection fromString(String s) => switch (s) {
        'inbound' => WebhookDirection.inbound,
        'outbound' => WebhookDirection.outbound,
        _ => WebhookDirection.inbound,
      };
}

/// Webhook health status.
enum WebhookHealthStatus {
  healthy,
  degraded,
  failing;

  static WebhookHealthStatus fromString(String s) => switch (s) {
        'healthy' => WebhookHealthStatus.healthy,
        'degraded' => WebhookHealthStatus.degraded,
        'failing' => WebhookHealthStatus.failing,
        _ => WebhookHealthStatus.healthy,
      };

  String get label => name[0].toUpperCase() + name.substring(1);
}

/// A registered webhook.
@immutable
class WebhookEntry {
  final String webhookId;
  final String name;
  final WebhookDirection direction;
  final String url;
  final String eventTypePrefix;
  final String signatureScheme;
  final String status;
  final String createdAt;
  final String updatedAt;

  const WebhookEntry({
    required this.webhookId,
    required this.name,
    this.direction = WebhookDirection.inbound,
    this.url = '',
    required this.eventTypePrefix,
    this.signatureScheme = 'hmac-sha256',
    this.status = 'active',
    this.createdAt = '',
    this.updatedAt = '',
  });

  factory WebhookEntry.fromJson(Map<String, dynamic> json) {
    return WebhookEntry(
      webhookId: json['webhook_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      direction:
          WebhookDirection.fromString(json['direction'] as String? ?? 'inbound'),
      url: json['url'] as String? ?? '',
      eventTypePrefix: json['event_type_prefix'] as String? ?? '',
      signatureScheme: json['signature_scheme'] as String? ?? 'hmac-sha256',
      status: json['status'] as String? ?? 'active',
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }

  bool get isActive => status == 'active';
}

/// Health summary for a webhook.
@immutable
class WebhookHealth {
  final String webhookId;
  final int eventCount;
  final int failureCount;
  final double failureRate;
  final int deadLetterCount;
  final String? lastReceivedAt;
  final WebhookHealthStatus status;

  const WebhookHealth({
    required this.webhookId,
    this.eventCount = 0,
    this.failureCount = 0,
    this.failureRate = 0,
    this.deadLetterCount = 0,
    this.lastReceivedAt,
    this.status = WebhookHealthStatus.healthy,
  });

  factory WebhookHealth.fromJson(Map<String, dynamic> json) {
    return WebhookHealth(
      webhookId: json['webhook_id'] as String? ?? '',
      eventCount: json['event_count'] as int? ?? 0,
      failureCount: json['failure_count'] as int? ?? 0,
      failureRate: (json['failure_rate'] as num?)?.toDouble() ?? 0,
      deadLetterCount: json['dead_letter_count'] as int? ?? 0,
      lastReceivedAt: json['last_received_at'] as String?,
      status: WebhookHealthStatus.fromString(
          json['status'] as String? ?? 'healthy'),
    );
  }
}

/// A webhook event log entry.
@immutable
class WebhookEvent {
  final String eventId;
  final String webhookId;
  final bool signatureValid;
  final String status;
  final int retryCount;
  final String? error;
  final String? processedAt;
  final String createdAt;

  const WebhookEvent({
    required this.eventId,
    required this.webhookId,
    this.signatureValid = false,
    this.status = 'received',
    this.retryCount = 0,
    this.error,
    this.processedAt,
    this.createdAt = '',
  });

  factory WebhookEvent.fromJson(Map<String, dynamic> json) {
    return WebhookEvent(
      eventId: json['event_id'] as String? ?? '',
      webhookId: json['webhook_id'] as String? ?? '',
      signatureValid: json['signature_valid'] as bool? ?? false,
      status: json['status'] as String? ?? 'received',
      retryCount: json['retry_count'] as int? ?? 0,
      error: json['error'] as String?,
      processedAt: json['processed_at'] as String?,
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}
