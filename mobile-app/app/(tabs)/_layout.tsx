import React from 'react';
import { Platform, StyleSheet } from 'react-native';
import { Tabs } from 'expo-router';
import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';

import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';

/**
 * Custom Tab Bar Icon using Ionicons for a consistent modern look
 */
function TabBarIcon(props: {
  name: React.ComponentProps<typeof Ionicons>['name'];
  color: string;
}) {
  return <Ionicons size={24} style={{ marginBottom: -3 }} {...props} />;
}

export default function TabLayout() {
  const colorScheme = useColorScheme();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        
        // Dark-themed Tab Bar Styling
        tabBarActiveTintColor: '#007AFF',
        tabBarInactiveTintColor: '#6E6E73',
        tabBarStyle: {
          backgroundColor: '#000000',
          borderTopColor: '#1C1C1E',
          borderTopWidth: 0.5,
          height: Platform.OS === 'ios' ? 88 : 70,
          paddingBottom: Platform.OS === 'ios' ? 30 : 12,
          paddingTop: 12,
          elevation: 0,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: -4 },
          shadowOpacity: 0.3,
          shadowRadius: 8,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '600',
          letterSpacing: 0.3,
        },
        tabBarItemStyle: {
          paddingVertical: 4,
        },
        tabBarBackground: () => 
          Platform.OS === 'ios' ? (
            <BlurView 
              intensity={100} 
              tint="dark" 
              style={StyleSheet.absoluteFill} 
            />
          ) : undefined,
      }}>
      
      <Tabs.Screen
        name="HomeScreen"
        options={{
          title: 'Chat',
          tabBarIcon: ({ color }) => <TabBarIcon name="chatbubble-ellipses" color={color} />,
        }}
      />
      
      <Tabs.Screen
        name="NotesScreen"
        options={{
          title: 'Notes',
          tabBarIcon: ({ color }) => <TabBarIcon name="journal" color={color} />,
        }}
      />
      
      <Tabs.Screen
        name="CalendarScreen"
        options={{
          title: 'Calendar',
          tabBarIcon: ({ color }) => <TabBarIcon name="calendar" color={color} />,
        }}
      />
    </Tabs>
  );
}