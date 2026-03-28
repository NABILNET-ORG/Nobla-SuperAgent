import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';
import 'package:nobla_agent/features/auth/screens/login_screen.dart';
import 'package:nobla_agent/features/auth/screens/register_screen.dart';
import 'package:nobla_agent/features/chat/screens/chat_screen.dart';
import 'package:nobla_agent/features/dashboard/screens/dashboard_screen.dart';
import 'package:nobla_agent/features/settings/screens/settings_screen.dart';
import 'package:nobla_agent/features/memory/screens/memory_viewer_screen.dart';
import 'package:nobla_agent/shared/widgets/kill_switch_fab.dart';
import 'package:nobla_agent/features/persona/screens/persona_list_screen.dart';
import 'package:nobla_agent/features/persona/screens/persona_detail_screen.dart';
import 'package:nobla_agent/features/persona/screens/persona_edit_screen.dart';
import 'package:nobla_agent/features/tools/screens/tools_screen.dart';
import 'package:nobla_agent/features/automation/screens/automation_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();
final _shellNavigatorKey = GlobalKey<NavigatorState>();

GoRouter createRouter(AuthState authState) {
  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/home/chat',
    redirect: (context, state) {
      final isAuthenticated = authState is Authenticated;
      final isAuthRoute = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';
      if (!isAuthenticated && !isAuthRoute) return '/login';
      if (isAuthenticated && isAuthRoute) return '/home/chat';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => const RegisterScreen(),
      ),
      ShellRoute(
        navigatorKey: _shellNavigatorKey,
        builder: (context, state, child) => HomeShell(child: child),
        routes: [
          GoRoute(
            path: '/home/chat',
            builder: (context, state) => const ChatScreen(),
          ),
          GoRoute(
            path: '/home/dashboard',
            builder: (context, state) => const DashboardScreen(),
          ),
          GoRoute(
            path: '/home/memory',
            builder: (context, state) => const MemoryViewerScreen(),
          ),
          GoRoute(
            path: '/home/persona',
            builder: (context, state) => const PersonaListScreen(),
          ),
          // create must stay before :id to avoid shadowing
          GoRoute(
            path: '/home/persona/create',
            builder: (context, state) => const PersonaEditScreen(),
          ),
          GoRoute(
            path: '/home/persona/:id',
            builder: (context, state) => PersonaDetailScreen(
              personaId: state.pathParameters['id']!,
            ),
          ),
          GoRoute(
            path: '/home/persona/:id/edit',
            builder: (context, state) => PersonaEditScreen(
              personaId: state.pathParameters['id']!,
            ),
          ),
          GoRoute(
            path: '/home/tools',
            builder: (context, state) => const ToolsScreen(),
          ),
          GoRoute(
            path: '/home/automation',
            builder: (context, state) => const AutomationScreen(),
          ),
          GoRoute(
            path: '/home/settings',
            builder: (context, state) => const SettingsScreen(),
          ),
        ],
      ),
    ],
  );
}

class HomeShell extends StatelessWidget {
  final Widget child;
  const HomeShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      floatingActionButton: const KillSwitchFab(),
      bottomNavigationBar: NavigationBar(
        selectedIndex:
            _calculateIndex(GoRouterState.of(context).matchedLocation),
        onDestinationSelected: (index) {
          switch (index) {
            case 0:
              context.go('/home/chat');
            case 1:
              context.go('/home/dashboard');
            case 2:
              context.go('/home/memory');
            case 3:
              context.go('/home/persona');
            case 4:
              context.go('/home/tools');
            case 5:
              context.go('/home/automation');
            case 6:
              context.go('/home/settings');
          }
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline),
            selectedIcon: Icon(Icons.chat_bubble),
            label: 'Chat',
          ),
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.memory_outlined),
            selectedIcon: Icon(Icons.memory),
            label: 'Memory',
          ),
          NavigationDestination(
            icon: Icon(Icons.face_outlined),
            selectedIcon: Icon(Icons.face),
            label: 'Persona',
          ),
          NavigationDestination(
            icon: Icon(Icons.build_outlined),
            selectedIcon: Icon(Icons.build),
            label: 'Tools',
          ),
          NavigationDestination(
            icon: Icon(Icons.account_tree_outlined),
            selectedIcon: Icon(Icons.account_tree),
            label: 'Automation',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
    );
  }

  int _calculateIndex(String location) {
    if (location.startsWith('/home/dashboard')) return 1;
    if (location.startsWith('/home/memory')) return 2;
    if (location.startsWith('/home/persona')) return 3;
    if (location.startsWith('/home/tools')) return 4;
    if (location.startsWith('/home/automation')) return 5;
    if (location.startsWith('/home/settings')) return 6;
    return 0;
  }
}
