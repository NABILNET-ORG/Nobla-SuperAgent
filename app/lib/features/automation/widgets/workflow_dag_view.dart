import 'package:flutter/material.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/widgets/step_node_widget.dart';
import 'package:nobla_agent/features/automation/widgets/step_bottom_sheet.dart';

/// Interactive DAG visualization for workflow steps.
///
/// Renders nodes positioned by [DagLayout] with directed edge arrows.
/// Nodes are tappable — opens [StepBottomSheet] with details and quick actions.
/// During live execution, nodes animate state changes via [executionStates].
class WorkflowDagView extends StatelessWidget {
  final List<WorkflowStep> steps;
  final DagLayout layout;
  final Map<String, ExecutionStatus> executionStates;
  final Map<String, StepExecutionResult>? stepResults;
  final double nodeWidth;
  final double nodeHeight;
  final void Function(WorkflowStep step)? onStepAction;

  const WorkflowDagView({
    super.key,
    required this.steps,
    required this.layout,
    this.executionStates = const {},
    this.stepResults,
    this.nodeWidth = 140,
    this.nodeHeight = 60,
    this.onStepAction,
  });

  @override
  Widget build(BuildContext context) {
    if (steps.isEmpty) {
      return Center(
        key: const ValueKey('dag_empty'),
        child: Text(
          'No steps defined',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.outline,
              ),
        ),
      );
    }

    final stepMap = {for (final s in steps) s.stepId: s};

    return InteractiveViewer(
      key: const ValueKey('dag_viewer'),
      boundaryMargin: const EdgeInsets.all(40),
      minScale: 0.5,
      maxScale: 2.0,
      child: SizedBox(
        width: layout.width + nodeWidth,
        height: layout.height + nodeHeight,
        child: Stack(
          children: [
            // Edges (painted behind nodes)
            CustomPaint(
              key: const ValueKey('dag_edges'),
              size: Size(layout.width + nodeWidth, layout.height + nodeHeight),
              painter: _EdgePainter(
                layout: layout,
                nodeWidth: nodeWidth,
                nodeHeight: nodeHeight,
                edgeColor: Theme.of(context).colorScheme.outlineVariant,
              ),
            ),
            // Nodes
            ...layout.nodes.map((dagNode) {
              final step = stepMap[dagNode.stepId];
              if (step == null) return const SizedBox.shrink();
              final execStatus = executionStates[dagNode.stepId];
              final result = stepResults?[dagNode.stepId];

              return Positioned(
                left: dagNode.x,
                top: dagNode.y,
                child: StepNodeWidget(
                  step: step,
                  executionStatus: execStatus,
                  branchTaken: result?.branchTaken,
                  width: nodeWidth,
                  height: nodeHeight,
                  onTap: () => _showStepSheet(context, step, result),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  void _showStepSheet(
    BuildContext context,
    WorkflowStep step,
    StepExecutionResult? result,
  ) {
    final execStatus = executionStates[step.stepId];
    showModalBottomSheet(
      context: context,
      builder: (ctx) => StepBottomSheet(
        step: step,
        executionResult: result,
        onRetry: execStatus == ExecutionStatus.failed
            ? () {
                Navigator.pop(ctx);
                onStepAction?.call(step);
              }
            : null,
        onSkip: execStatus == ExecutionStatus.pending ||
                execStatus == ExecutionStatus.running
            ? () {
                Navigator.pop(ctx);
                onStepAction?.call(step);
              }
            : null,
      ),
    );
  }
}

/// Custom painter for directed edges between DAG nodes.
class _EdgePainter extends CustomPainter {
  final DagLayout layout;
  final double nodeWidth;
  final double nodeHeight;
  final Color edgeColor;

  _EdgePainter({
    required this.layout,
    required this.nodeWidth,
    required this.nodeHeight,
    required this.edgeColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = edgeColor
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    final arrowPaint = Paint()
      ..color = edgeColor
      ..style = PaintingStyle.fill;

    final nodeMap = {for (final n in layout.nodes) n.stepId: n};

    for (final (fromId, toId) in layout.edges) {
      final from = nodeMap[fromId];
      final to = nodeMap[toId];
      if (from == null || to == null) continue;

      final startX = from.x + nodeWidth;
      final startY = from.y + nodeHeight / 2;
      final endX = to.x;
      final endY = to.y + nodeHeight / 2;

      // Draw curved path
      final path = Path()
        ..moveTo(startX, startY)
        ..cubicTo(
          startX + (endX - startX) * 0.4,
          startY,
          endX - (endX - startX) * 0.4,
          endY,
          endX,
          endY,
        );
      canvas.drawPath(path, paint);

      // Arrowhead
      const arrowSize = 6.0;
      final arrowPath = Path()
        ..moveTo(endX, endY)
        ..lineTo(endX - arrowSize, endY - arrowSize / 2)
        ..lineTo(endX - arrowSize, endY + arrowSize / 2)
        ..close();
      canvas.drawPath(arrowPath, arrowPaint);
    }
  }

  @override
  bool shouldRepaint(_EdgePainter old) =>
      layout != old.layout || edgeColor != old.edgeColor;
}
