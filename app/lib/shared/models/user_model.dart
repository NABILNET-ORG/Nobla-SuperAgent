class UserModel {
  final String userId;
  final String displayName;
  final int tier;

  const UserModel({
    required this.userId,
    required this.displayName,
    this.tier = 1,
  });

  UserModel copyWith({int? tier, String? displayName}) {
    return UserModel(
      userId: userId,
      displayName: displayName ?? this.displayName,
      tier: tier ?? this.tier,
    );
  }

  String get tierName {
    switch (tier) {
      case 1:
        return 'SAFE';
      case 2:
        return 'STANDARD';
      case 3:
        return 'ELEVATED';
      case 4:
        return 'ADMIN';
      default:
        return 'UNKNOWN';
    }
  }
}
