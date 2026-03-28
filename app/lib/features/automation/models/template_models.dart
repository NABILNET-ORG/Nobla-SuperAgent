import 'package:flutter/foundation.dart';

/// Template category for discovery and filtering.
enum TemplateCategory {
  ciCd,
  notifications,
  dataPipeline,
  devops,
  approval,
  integration,
  monitoring,
  custom;

  static TemplateCategory fromString(String s) => switch (s) {
        'ci_cd' => TemplateCategory.ciCd,
        'notifications' => TemplateCategory.notifications,
        'data_pipeline' => TemplateCategory.dataPipeline,
        'devops' => TemplateCategory.devops,
        'approval' => TemplateCategory.approval,
        'integration' => TemplateCategory.integration,
        'monitoring' => TemplateCategory.monitoring,
        'custom' => TemplateCategory.custom,
        _ => TemplateCategory.custom,
      };

  String get value => switch (this) {
        TemplateCategory.ciCd => 'ci_cd',
        TemplateCategory.notifications => 'notifications',
        TemplateCategory.dataPipeline => 'data_pipeline',
        TemplateCategory.devops => 'devops',
        TemplateCategory.approval => 'approval',
        TemplateCategory.integration => 'integration',
        TemplateCategory.monitoring => 'monitoring',
        TemplateCategory.custom => 'custom',
      };

  String get label => switch (this) {
        TemplateCategory.ciCd => 'CI/CD',
        TemplateCategory.notifications => 'Notifications',
        TemplateCategory.dataPipeline => 'Data Pipeline',
        TemplateCategory.devops => 'DevOps',
        TemplateCategory.approval => 'Approval',
        TemplateCategory.integration => 'Integration',
        TemplateCategory.monitoring => 'Monitoring',
        TemplateCategory.custom => 'Custom',
      };

  String get icon => switch (this) {
        TemplateCategory.ciCd => '🔄',
        TemplateCategory.notifications => '🔔',
        TemplateCategory.dataPipeline => '📊',
        TemplateCategory.devops => '🛠',
        TemplateCategory.approval => '✅',
        TemplateCategory.integration => '🔗',
        TemplateCategory.monitoring => '📡',
        TemplateCategory.custom => '⚙',
      };
}

/// Portable step definition for templates.
@immutable
class TemplateStep {
  final String refId;
  final String name;
  final String type;
  final Map<String, dynamic> config;
  final List<String> dependsOn;
  final String errorHandling;
  final int maxRetries;
  final int? timeoutSeconds;
  final String description;

  const TemplateStep({
    required this.refId,
    required this.name,
    this.type = 'tool',
    this.config = const {},
    this.dependsOn = const [],
    this.errorHandling = 'fail',
    this.maxRetries = 0,
    this.timeoutSeconds,
    this.description = '',
  });

  factory TemplateStep.fromJson(Map<String, dynamic> json) {
    return TemplateStep(
      refId: json['ref_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      type: json['type'] as String? ?? 'tool',
      config: Map<String, dynamic>.from(json['config'] as Map? ?? {}),
      dependsOn: (json['depends_on'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      errorHandling: json['error_handling'] as String? ?? 'fail',
      maxRetries: json['max_retries'] as int? ?? 0,
      timeoutSeconds: json['timeout_seconds'] as int?,
      description: json['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'ref_id': refId,
      'name': name,
      'type': type,
      'config': config,
      'depends_on': dependsOn,
      'error_handling': errorHandling,
      'max_retries': maxRetries,
    };
    if (timeoutSeconds != null) map['timeout_seconds'] = timeoutSeconds;
    if (description.isNotEmpty) map['description'] = description;
    return map;
  }
}

/// Portable trigger definition for templates.
@immutable
class TemplateTrigger {
  final String eventPattern;
  final List<Map<String, dynamic>> conditions;
  final String description;

  const TemplateTrigger({
    this.eventPattern = '*',
    this.conditions = const [],
    this.description = '',
  });

  factory TemplateTrigger.fromJson(Map<String, dynamic> json) {
    return TemplateTrigger(
      eventPattern: json['event_pattern'] as String? ?? '*',
      conditions: (json['conditions'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          [],
      description: json['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'event_pattern': eventPattern,
      'conditions': conditions,
    };
    if (description.isNotEmpty) map['description'] = description;
    return map;
  }
}

/// Workflow template summary (from list endpoint).
@immutable
class WorkflowTemplate {
  final String templateId;
  final String name;
  final String description;
  final TemplateCategory category;
  final List<String> tags;
  final String author;
  final String version;
  final int stepCount;
  final int triggerCount;
  final String icon;
  final bool bundled;

  const WorkflowTemplate({
    required this.templateId,
    required this.name,
    this.description = '',
    this.category = TemplateCategory.custom,
    this.tags = const [],
    this.author = '',
    this.version = '1.0.0',
    this.stepCount = 0,
    this.triggerCount = 0,
    this.icon = '',
    this.bundled = false,
  });

  factory WorkflowTemplate.fromJson(Map<String, dynamic> json) {
    return WorkflowTemplate(
      templateId: json['template_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      category: TemplateCategory.fromString(json['category'] as String? ?? ''),
      tags: (json['tags'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      author: json['author'] as String? ?? '',
      version: json['version'] as String? ?? '1.0.0',
      stepCount: json['step_count'] as int? ?? 0,
      triggerCount: json['trigger_count'] as int? ?? 0,
      icon: json['icon'] as String? ?? '',
      bundled: json['bundled'] as bool? ?? false,
    );
  }
}

/// Full template detail (from detail endpoint).
@immutable
class WorkflowTemplateDetail extends WorkflowTemplate {
  final List<TemplateStep> steps;
  final List<TemplateTrigger> triggers;
  final String createdAt;
  final String updatedAt;

  const WorkflowTemplateDetail({
    required super.templateId,
    required super.name,
    super.description,
    super.category,
    super.tags,
    super.author,
    super.version,
    super.stepCount,
    super.triggerCount,
    super.icon,
    super.bundled,
    this.steps = const [],
    this.triggers = const [],
    this.createdAt = '',
    this.updatedAt = '',
  });

  factory WorkflowTemplateDetail.fromJson(Map<String, dynamic> json) {
    return WorkflowTemplateDetail(
      templateId: json['template_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      category: TemplateCategory.fromString(json['category'] as String? ?? ''),
      tags: (json['tags'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      author: json['author'] as String? ?? '',
      version: json['version'] as String? ?? '1.0.0',
      stepCount: json['step_count'] as int? ?? 0,
      triggerCount: json['trigger_count'] as int? ?? 0,
      icon: json['icon'] as String? ?? '',
      bundled: json['bundled'] as bool? ?? false,
      steps: (json['steps'] as List<dynamic>?)
              ?.map((s) => TemplateStep.fromJson(s as Map<String, dynamic>))
              .toList() ??
          [],
      triggers: (json['triggers'] as List<dynamic>?)
              ?.map((t) => TemplateTrigger.fromJson(t as Map<String, dynamic>))
              .toList() ??
          [],
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }
}

/// Export data envelope for workflow import/export.
@immutable
class WorkflowExportData {
  final String noblaVersion;
  final String exportedAt;
  final String sourceWorkflowId;
  final int sourceWorkflowVersion;
  final String name;
  final String description;
  final List<TemplateStep> steps;
  final List<TemplateTrigger> triggers;
  final Map<String, dynamic> metadata;

  const WorkflowExportData({
    this.noblaVersion = '1.0',
    this.exportedAt = '',
    this.sourceWorkflowId = '',
    this.sourceWorkflowVersion = 1,
    this.name = '',
    this.description = '',
    this.steps = const [],
    this.triggers = const [],
    this.metadata = const {},
  });

  factory WorkflowExportData.fromJson(Map<String, dynamic> json) {
    final source = json['source'] as Map<String, dynamic>? ?? {};
    final workflow = json['workflow'] as Map<String, dynamic>? ?? {};
    return WorkflowExportData(
      noblaVersion: json[r'$nobla_version'] as String? ?? '',
      exportedAt: json['exported_at'] as String? ?? '',
      sourceWorkflowId: source['workflow_id'] as String? ?? '',
      sourceWorkflowVersion: source['workflow_version'] as int? ?? 1,
      name: workflow['name'] as String? ?? '',
      description: workflow['description'] as String? ?? '',
      steps: (workflow['steps'] as List<dynamic>?)
              ?.map((s) => TemplateStep.fromJson(s as Map<String, dynamic>))
              .toList() ??
          [],
      triggers: (workflow['triggers'] as List<dynamic>?)
              ?.map((t) => TemplateTrigger.fromJson(t as Map<String, dynamic>))
              .toList() ??
          [],
      metadata:
          Map<String, dynamic>.from(json['metadata'] as Map? ?? {}),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      r'$nobla_version': noblaVersion,
      'exported_at': exportedAt,
      'source': {
        'workflow_id': sourceWorkflowId,
        'workflow_version': sourceWorkflowVersion,
      },
      'workflow': {
        'name': name,
        'description': description,
        'steps': steps.map((s) => s.toJson()).toList(),
        'triggers': triggers.map((t) => t.toJson()).toList(),
      },
      'metadata': metadata,
    };
  }
}

/// Category with template count (from categories endpoint).
@immutable
class CategoryInfo {
  final String category;
  final String label;
  final int count;

  const CategoryInfo({
    required this.category,
    required this.label,
    required this.count,
  });

  factory CategoryInfo.fromJson(Map<String, dynamic> json) {
    return CategoryInfo(
      category: json['category'] as String? ?? '',
      label: json['label'] as String? ?? '',
      count: json['count'] as int? ?? 0,
    );
  }
}
