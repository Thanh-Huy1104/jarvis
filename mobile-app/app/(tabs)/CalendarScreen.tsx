import React, { useState, useEffect } from 'react';
import { StyleSheet, FlatList } from 'react-native';
import { Text, View } from '@/components/Themed';
import { getCalendarEvents } from '../../services/api';

interface CalendarEvent {
  id: string;
  title: string;
  startDate: string;
  endDate: string;
}

export default function CalendarScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const fetchedEvents = await getCalendarEvents();
        setEvents(fetchedEvents);
      } catch (error) {
        // Handle error
      }
    };

    fetchEvents();
  }, []);

  return (
    <View style={styles.container}>
      <FlatList
        data={events}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <View style={styles.eventContainer}>
            <Text style={styles.eventTitle}>{item.title}</Text>
            <Text>Start: {new Date(item.startDate).toLocaleString()}</Text>
            <Text>End: {new Date(item.endDate).toLocaleString()}</Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 10,
  },
  eventContainer: {
    padding: 10,
    borderRadius: 5,
    marginVertical: 5,
    backgroundColor: '#fff',
  },
  eventTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 5,
  },
});
