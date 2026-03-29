import 'package:flutter/foundation.dart';

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

enum PatternStatus { detected, confirmed, skillCreated, dismissed }

enum MacroTier { macro, skill, publishable }

enum ExperimentStatus { running, concluded, paused }

enum SuggestionType { pattern, optimization, anomaly, briefing }

enum SuggestionStatus { pending, accepted, dismissed, snoozed, expired }

enum ProactiveLevel { off, conservative, moderate, aggressive }

// ---------------------------------------------------------------------------
// Enum helper
// ---------------------------------------------------------------------------

T _enumFromString<T>(List<T> values, String? value, T defaultValue) {
  if (value == null) return defaultValue;
  final normalized = value.replaceAll('_', '').toLowerCase();
  return values.firstWhere(
    (e) {
      // toString() returns 'EnumName.valueName' — extract the value part
      final enumName = e.toString().split('.').last.toLowerCase();
      return enumName == normalized || enumName == value.toLowerCase();
    },
    orElse: () => defaultValue,
  );
}

// ---------------------------------------------------------------------------
// FeedbackContext
// ---------------------------------------------------------------------------

@immutable
class FeedbackContext {
  final String llmModel;
  final String promptTemplate;
  final List<String> toolChain;
  final String intentCategory;
  final String? abVariantId;

  const FeedbackContext({
    required this.llmModel,
    this.promptTemplate = '',
    this.toolChain = const [],
    this.intentCategory = '',
    this.abVariantId,
  });

  factory FeedbackContext.fromJson(Map<String, dynamic> json) {
    return FeedbackContext(
      llmModel: json['llm_model'] as String? ?? '',
      promptTemplate: json['prompt_template'] as String? ?? '',
      toolChain: List<String>.from(json['tool_chain'] as List? ?? []),
      intentCategory: json['intent_category'] as String? ?? '',
      abVariantId: json['ab_variant_id'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'llm_model': llmModel,
        'prompt_template': promptTemplate,
        'tool_chain': toolChain,
        'intent_category': intentCategory,
        if (abVariantId != null) 'ab_variant_id': abVariantId,
      };
}

// ---------------------------------------------------------------------------
// ResponseFeedback
// ---------------------------------------------------------------------------

@immutable
class ResponseFeedback {
  final String id;
  final String conversationId;
  final String messageId;
  final String userId;
  final int quickRating;
  final int? starRating;
  final String? comment;
  final FeedbackContext context;
  final DateTime timestamp;

  const ResponseFeedback({
    required this.id,
    required this.conversationId,
    required this.messageId,
    required this.userId,
    required this.quickRating,
    this.starRating,
    this.comment,
    required this.context,
    required this.timestamp,
  });

  bool get isPositive => quickRating > 0;
  bool get isNegative => quickRating < 0;

  factory ResponseFeedback.fromJson(Map<String, dynamic> json) {
    return ResponseFeedback(
      id: json['id'] as String? ?? '',
      conversationId: json['conversation_id'] as String? ?? '',
      messageId: json['message_id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      quickRating: json['quick_rating'] as int? ?? 0,
      starRating: json['star_rating'] as int?,
      comment: json['comment'] as String?,
      context: FeedbackContext.fromJson(
          json['context'] as Map<String, dynamic>? ?? {}),
      timestamp:
          DateTime.tryParse(json['timestamp'] as String? ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'conversation_id': conversationId,
        'message_id': messageId,
        'user_id': userId,
        'quick_rating': quickRating,
        if (starRating != null) 'star_rating': starRating,
        if (comment != null) 'comment': comment,
        'context': context.toJson(),
        'timestamp': timestamp.toIso8601String(),
      };
}

// ---------------------------------------------------------------------------
// PatternOccurrence
// ---------------------------------------------------------------------------

@immutable
class PatternOccurrence {
  final DateTime timestamp;
  final String conversationId;
  final Map<String, dynamic> params;

  const PatternOccurrence({
    required this.timestamp,
    required this.conversationId,
    this.params = const {},
  });

  factory PatternOccurrence.fromJson(Map<String, dynamic> json) {
    return PatternOccurrence(
      timestamp:
          DateTime.tryParse(json['timestamp'] as String? ?? '') ?? DateTime.now(),
      conversationId: json['conversation_id'] as String? ?? '',
      params: Map<String, dynamic>.from(json['params'] as Map? ?? {}),
    );
  }

  Map<String, dynamic> toJson() => {
        'timestamp': timestamp.toIso8601String(),
        'conversation_id': conversationId,
        'params': params,
      };
}

// ---------------------------------------------------------------------------
// PatternCandidate
// ---------------------------------------------------------------------------

@immutable
class PatternCandidate {
  final String id;
  final String userId;
  final String fingerprint;
  final String description;
  final List<PatternOccurrence> occurrences;
  final List<String> toolSequence;
  final Map<String, dynamic> variableParams;
  final PatternStatus status;
  final double confidence;
  final String detectionMethod;
  final DateTime createdAt;

  const PatternCandidate({
    required this.id,
    required this.userId,
    required this.fingerprint,
    required this.description,
    required this.occurrences,
    required this.toolSequence,
    this.variableParams = const {},
    required this.status,
    required this.confidence,
    required this.detectionMethod,
    required this.createdAt,
  });

  factory PatternCandidate.fromJson(Map<String, dynamic> json) {
    // Handle skill_created -> skillCreated mapping
    String? rawStatus = json['status'] as String?;
    PatternStatus parsedStatus;
    if (rawStatus == 'skill_created') {
      parsedStatus = PatternStatus.skillCreated;
    } else {
      parsedStatus = _enumFromString(
          PatternStatus.values, rawStatus, PatternStatus.detected);
    }

    return PatternCandidate(
      id: json['id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      fingerprint: json['fingerprint'] as String? ?? '',
      description: json['description'] as String? ?? '',
      occurrences: (json['occurrences'] as List? ?? [])
          .map((e) => PatternOccurrence.fromJson(e as Map<String, dynamic>))
          .toList(),
      toolSequence: List<String>.from(json['tool_sequence'] as List? ?? []),
      variableParams:
          Map<String, dynamic>.from(json['variable_params'] as Map? ?? {}),
      status: parsedStatus,
      confidence: (json['confidence'] as num? ?? 0.0).toDouble(),
      detectionMethod: json['detection_method'] as String? ?? '',
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'user_id': userId,
        'fingerprint': fingerprint,
        'description': description,
        'occurrences': occurrences.map((o) => o.toJson()).toList(),
        'tool_sequence': toolSequence,
        'variable_params': variableParams,
        'status': status.name,
        'confidence': confidence,
        'detection_method': detectionMethod,
        'created_at': createdAt.toIso8601String(),
      };
}

// ---------------------------------------------------------------------------
// MacroParameter
// ---------------------------------------------------------------------------

@immutable
class MacroParameter {
  final String name;
  final String description;
  final String type;
  final dynamic defaultValue;
  final List<dynamic> examples;

  const MacroParameter({
    required this.name,
    this.description = '',
    this.type = 'string',
    this.defaultValue,
    this.examples = const [],
  });

  factory MacroParameter.fromJson(Map<String, dynamic> json) {
    return MacroParameter(
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      type: json['type'] as String? ?? 'string',
      defaultValue: json['default_value'],
      examples: List<dynamic>.from(json['examples'] as List? ?? []),
    );
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'description': description,
        'type': type,
        if (defaultValue != null) 'default_value': defaultValue,
        'examples': examples,
      };
}

// ---------------------------------------------------------------------------
// WorkflowMacro
// ---------------------------------------------------------------------------

@immutable
class WorkflowMacro {
  final String id;
  final String name;
  final String description;
  final String patternId;
  final String? workflowId;
  final String? skillId;
  final List<MacroParameter> parameters;
  final MacroTier tier;
  final int usageCount;
  final String userId;
  final DateTime createdAt;
  final DateTime? promotedAt;

  const WorkflowMacro({
    required this.id,
    required this.name,
    required this.description,
    required this.patternId,
    this.workflowId,
    this.skillId,
    this.parameters = const [],
    required this.tier,
    this.usageCount = 0,
    required this.userId,
    required this.createdAt,
    this.promotedAt,
  });

  factory WorkflowMacro.fromJson(Map<String, dynamic> json) {
    return WorkflowMacro(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      patternId: json['pattern_id'] as String? ?? '',
      workflowId: json['workflow_id'] as String?,
      skillId: json['skill_id'] as String?,
      parameters: (json['parameters'] as List? ?? [])
          .map((e) => MacroParameter.fromJson(e as Map<String, dynamic>))
          .toList(),
      tier: _enumFromString(MacroTier.values, json['tier'] as String?,
          MacroTier.macro),
      usageCount: json['usage_count'] as int? ?? 0,
      userId: json['user_id'] as String? ?? '',
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      promotedAt: json['promoted_at'] != null
          ? DateTime.tryParse(json['promoted_at'] as String)
          : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'description': description,
        'pattern_id': patternId,
        if (workflowId != null) 'workflow_id': workflowId,
        if (skillId != null) 'skill_id': skillId,
        'parameters': parameters.map((p) => p.toJson()).toList(),
        'tier': tier.name,
        'usage_count': usageCount,
        'user_id': userId,
        'created_at': createdAt.toIso8601String(),
        if (promotedAt != null) 'promoted_at': promotedAt!.toIso8601String(),
      };
}

// ---------------------------------------------------------------------------
// ABVariant
// ---------------------------------------------------------------------------

@immutable
class ABVariant {
  final String id;
  final String model;
  final String? promptTemplate;
  final List<double> feedbackScores;
  final int sampleCount;
  final double winRate;

  const ABVariant({
    required this.id,
    required this.model,
    this.promptTemplate,
    this.feedbackScores = const [],
    this.sampleCount = 0,
    this.winRate = 0.0,
  });

  factory ABVariant.fromJson(Map<String, dynamic> json) {
    return ABVariant(
      id: json['id'] as String? ?? '',
      model: json['model'] as String? ?? '',
      promptTemplate: json['prompt_template'] as String?,
      feedbackScores: (json['feedback_scores'] as List? ?? [])
          .map((e) => (e as num).toDouble())
          .toList(),
      sampleCount: json['sample_count'] as int? ?? 0,
      winRate: (json['win_rate'] as num? ?? 0.0).toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'model': model,
        if (promptTemplate != null) 'prompt_template': promptTemplate,
        'feedback_scores': feedbackScores,
        'sample_count': sampleCount,
        'win_rate': winRate,
      };
}

// ---------------------------------------------------------------------------
// ABExperiment
// ---------------------------------------------------------------------------

@immutable
class ABExperiment {
  final String id;
  final String taskCategory;
  final List<ABVariant> variants;
  final ExperimentStatus status;
  final int minSamples;
  final double epsilon;
  final DateTime createdAt;
  final DateTime? concludedAt;
  final String? winnerVariantId;

  const ABExperiment({
    required this.id,
    required this.taskCategory,
    required this.variants,
    required this.status,
    this.minSamples = 20,
    this.epsilon = 0.1,
    required this.createdAt,
    this.concludedAt,
    this.winnerVariantId,
  });

  factory ABExperiment.fromJson(Map<String, dynamic> json) {
    return ABExperiment(
      id: json['id'] as String? ?? '',
      taskCategory: json['task_category'] as String? ?? '',
      variants: (json['variants'] as List? ?? [])
          .map((e) => ABVariant.fromJson(e as Map<String, dynamic>))
          .toList(),
      status: _enumFromString(ExperimentStatus.values, json['status'] as String?,
          ExperimentStatus.running),
      minSamples: json['min_samples'] as int? ?? 20,
      epsilon: (json['epsilon'] as num? ?? 0.1).toDouble(),
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      concludedAt: json['concluded_at'] != null
          ? DateTime.tryParse(json['concluded_at'] as String)
          : null,
      winnerVariantId: json['winner_variant_id'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'task_category': taskCategory,
        'variants': variants.map((v) => v.toJson()).toList(),
        'status': status.name,
        'min_samples': minSamples,
        'epsilon': epsilon,
        'created_at': createdAt.toIso8601String(),
        if (concludedAt != null) 'concluded_at': concludedAt!.toIso8601String(),
        if (winnerVariantId != null) 'winner_variant_id': winnerVariantId,
      };
}

// ---------------------------------------------------------------------------
// ProactiveSuggestion
// ---------------------------------------------------------------------------

@immutable
class ProactiveSuggestion {
  final String id;
  final SuggestionType type;
  final String title;
  final String description;
  final double confidence;
  final Map<String, dynamic>? action;
  final String userId;
  final SuggestionStatus status;
  final DateTime? snoozeUntil;
  final int snoozeCount;
  final DateTime? expiresAt;
  final DateTime createdAt;
  final String? sourcePatternId;

  const ProactiveSuggestion({
    required this.id,
    required this.type,
    required this.title,
    required this.description,
    required this.confidence,
    this.action,
    required this.userId,
    this.status = SuggestionStatus.pending,
    this.snoozeUntil,
    this.snoozeCount = 0,
    this.expiresAt,
    required this.createdAt,
    this.sourcePatternId,
  });

  factory ProactiveSuggestion.fromJson(Map<String, dynamic> json) {
    return ProactiveSuggestion(
      id: json['id'] as String? ?? '',
      type: _enumFromString(
          SuggestionType.values, json['type'] as String?, SuggestionType.pattern),
      title: json['title'] as String? ?? '',
      description: json['description'] as String? ?? '',
      confidence: (json['confidence'] as num? ?? 0.0).toDouble(),
      action: json['action'] != null
          ? Map<String, dynamic>.from(json['action'] as Map)
          : null,
      userId: json['user_id'] as String? ?? '',
      status: _enumFromString(SuggestionStatus.values, json['status'] as String?,
          SuggestionStatus.pending),
      snoozeUntil: json['snooze_until'] != null
          ? DateTime.tryParse(json['snooze_until'] as String)
          : null,
      snoozeCount: json['snooze_count'] as int? ?? 0,
      expiresAt: json['expires_at'] != null
          ? DateTime.tryParse(json['expires_at'] as String)
          : null,
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      sourcePatternId: json['source_pattern_id'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.name,
        'title': title,
        'description': description,
        'confidence': confidence,
        if (action != null) 'action': action,
        'user_id': userId,
        'status': status.name,
        if (snoozeUntil != null) 'snooze_until': snoozeUntil!.toIso8601String(),
        'snooze_count': snoozeCount,
        if (expiresAt != null) 'expires_at': expiresAt!.toIso8601String(),
        'created_at': createdAt.toIso8601String(),
        if (sourcePatternId != null) 'source_pattern_id': sourcePatternId,
      };
}

// ---------------------------------------------------------------------------
// LearningSettings
// ---------------------------------------------------------------------------

@immutable
class LearningSettings {
  final bool enabled;
  final bool feedbackEnabled;
  final bool patternDetectionEnabled;
  final bool abTestingEnabled;
  final ProactiveLevel proactiveLevel;

  const LearningSettings({
    this.enabled = true,
    this.feedbackEnabled = true,
    this.patternDetectionEnabled = true,
    this.abTestingEnabled = true,
    this.proactiveLevel = ProactiveLevel.conservative,
  });

  factory LearningSettings.fromJson(Map<String, dynamic> json) {
    return LearningSettings(
      enabled: json['enabled'] as bool? ?? true,
      feedbackEnabled: json['feedback_enabled'] as bool? ?? true,
      patternDetectionEnabled:
          json['pattern_detection_enabled'] as bool? ?? true,
      abTestingEnabled: json['ab_testing_enabled'] as bool? ?? true,
      proactiveLevel: _enumFromString(ProactiveLevel.values,
          json['proactive_level'] as String?, ProactiveLevel.conservative),
    );
  }

  Map<String, dynamic> toJson() => {
        'enabled': enabled,
        'feedback_enabled': feedbackEnabled,
        'pattern_detection_enabled': patternDetectionEnabled,
        'ab_testing_enabled': abTestingEnabled,
        'proactive_level': proactiveLevel.name,
      };
}
