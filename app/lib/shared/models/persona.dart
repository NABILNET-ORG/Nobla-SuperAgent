class Persona {
  final String id;
  final String name;
  final String personality;
  final String languageStyle;
  final String? background;
  final Map<String, dynamic>? voiceConfig;
  final List<String> rules;
  final double? temperatureBias;
  final int? maxResponseLength;
  final bool isBuiltin;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const Persona({
    required this.id,
    required this.name,
    required this.personality,
    required this.languageStyle,
    this.background,
    this.voiceConfig,
    this.rules = const [],
    this.temperatureBias,
    this.maxResponseLength,
    this.isBuiltin = false,
    this.createdAt,
    this.updatedAt,
  });

  factory Persona.fromJson(Map<String, dynamic> json) {
    return Persona(
      id: json['id'] as String,
      name: json['name'] as String,
      personality: json['personality'] as String,
      languageStyle: json['language_style'] as String,
      background: json['background'] as String?,
      voiceConfig: json['voice_config'] as Map<String, dynamic>?,
      rules:
          (json['rules'] as List<dynamic>?)?.map((e) => e as String).toList() ??
              const [],
      temperatureBias: (json['temperature_bias'] as num?)?.toDouble(),
      maxResponseLength: json['max_response_length'] as int?,
      isBuiltin: json['is_builtin'] as bool? ?? false,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at'] as String)
          : null,
    );
  }

  /// Produces JSON for create/update requests (excludes server-assigned fields).
  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'personality': personality,
      'language_style': languageStyle,
      if (background != null) 'background': background,
      if (voiceConfig != null) 'voice_config': voiceConfig,
      'rules': rules,
      if (temperatureBias != null) 'temperature_bias': temperatureBias,
      if (maxResponseLength != null) 'max_response_length': maxResponseLength,
    };
  }

  Persona copyWith({
    String? name,
    String? personality,
    String? languageStyle,
    String? background,
    Map<String, dynamic>? voiceConfig,
    List<String>? rules,
    double? temperatureBias,
    int? maxResponseLength,
  }) {
    return Persona(
      id: id,
      name: name ?? this.name,
      personality: personality ?? this.personality,
      languageStyle: languageStyle ?? this.languageStyle,
      background: background ?? this.background,
      voiceConfig: voiceConfig ?? this.voiceConfig,
      rules: rules ?? this.rules,
      temperatureBias: temperatureBias ?? this.temperatureBias,
      maxResponseLength: maxResponseLength ?? this.maxResponseLength,
      isBuiltin: isBuiltin,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}

class PersonaPreference {
  final String? defaultPersonaId;

  const PersonaPreference({this.defaultPersonaId});

  factory PersonaPreference.fromJson(Map<String, dynamic> json) {
    return PersonaPreference(
      defaultPersonaId: json['default_persona_id'] as String?,
    );
  }
}
