import 'package:dio/dio.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class ApiClient {
  final Dio _dio;

  /// Production constructor — creates Dio with base URL and auth interceptor.
  ApiClient({
    required String baseUrl,
    required String Function() getUserId,
  }) : _dio = Dio(BaseOptions(baseUrl: baseUrl)) {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        options.headers['X-User-Id'] = getUserId();
        handler.next(options);
      },
    ));
  }

  /// Test constructor — accepts a pre-configured Dio instance.
  ApiClient.withDio(this._dio);

  // -- Persona CRUD --

  Future<List<Persona>> listPersonas() async {
    final response = await _dio.get('/api/personas');
    final list = response.data as List<dynamic>;
    return list
        .map((e) => Persona.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Persona> getPersona(String id) async {
    final response = await _dio.get('/api/personas/$id');
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Persona> createPersona(Map<String, dynamic> body) async {
    final response = await _dio.post('/api/personas', data: body);
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Persona> updatePersona(String id, Map<String, dynamic> body) async {
    final response = await _dio.put('/api/personas/$id', data: body);
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  Future<void> deletePersona(String id) async {
    await _dio.delete('/api/personas/$id');
  }

  Future<Persona> clonePersona(String id) async {
    final response = await _dio.post('/api/personas/$id/clone');
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  // -- User Preference --

  Future<PersonaPreference> getPreference() async {
    final response = await _dio.get('/api/user/persona-preference');
    return PersonaPreference.fromJson(response.data as Map<String, dynamic>);
  }

  Future<PersonaPreference> setPreference(String personaId) async {
    final response = await _dio.put(
      '/api/user/persona-preference',
      data: {'default_persona_id': personaId},
    );
    return PersonaPreference.fromJson(response.data as Map<String, dynamic>);
  }
}
