import 'package:flutter/material.dart';
import '../models/marketplace_models.dart';

class VersionListWidget extends StatelessWidget {
  final List<SkillVersion> versions;

  const VersionListWidget({super.key, required this.versions});

  @override
  Widget build(BuildContext context) {
    if (versions.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Text('No version history available.'),
      );
    }
    return ListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: versions.length,
      itemBuilder: (context, index) {
        final v = versions[versions.length - 1 - index]; // newest first
        return ExpansionTile(
          title: Text('v${v.version}'),
          subtitle: Text(
            _formatDate(v.publishedAt),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          trailing: v.scanPassed
              ? Icon(Icons.verified, color: Colors.green.shade600, size: 18)
              : const Icon(Icons.warning_amber, color: Colors.orange, size: 18),
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(v.changelog),
              ),
            ),
          ],
        );
      },
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
  }
}
