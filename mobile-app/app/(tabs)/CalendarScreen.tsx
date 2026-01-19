import React, { useState, useEffect, useMemo } from 'react';
import { 
  StyleSheet, 
  FlatList, 
  TouchableOpacity, 
  Animated, 
  Dimensions, 
  Platform,
  LayoutAnimation,
  UIManager
} from 'react-native';
import { Text, View } from '@/components/Themed';
import { getCalendarEvents } from '../../services/api';

// Enable LayoutAnimation for Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface CalendarEvent {
  id: string;
  title: string;
  startDate: string;
  endDate: string;
}

const { width } = Dimensions.get('window');
const DAY_WIDTH = width / 7;

export default function CalendarScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [loading, setLoading] = useState(true);

  // Generate 14 days for the slider (past week + current week)
  const weekDays = useMemo(() => {
    const days = [];
    const start = new Date();
    start.setDate(start.getDate() - 3); // Start 3 days ago
    for (let i = 0; i < 14; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      days.push(d);
    }
    return days;
  }, []);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        setLoading(true);
        const fetchedData = await getCalendarEvents();
        if (fetchedData && fetchedData.events) {
          const transformedEvents = fetchedData.events.map((event: any) => {
            const startDate = new Date(event.event_datetime);
            const endDate = new Date(startDate.getTime() + event.duration_minutes * 60000);
            return {
              id: event.id,
              title: event.title,
              startDate: startDate.toISOString(),
              endDate: endDate.toISOString(),
            };
          });
          setEvents(transformedEvents);
        }
      } catch (error) {
        console.error('Error fetching calendar events:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchEvents();
  }, []);

  const filteredEvents = useMemo(() => {
    return events.filter(event => {
      const d = new Date(event.startDate);
      return d.toDateString() === selectedDate.toDateString();
    });
  }, [events, selectedDate]);

  const onDateSelect = (date: Date) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setSelectedDate(date);
  };

  const renderDay = ({ item }: { item: Date }) => {
    const isSelected = item.toDateString() === selectedDate.toDateString();
    const dayName = item.toLocaleDateString('en-US', { weekday: 'short' });
    const dayNum = item.getDate();

    return (
      <TouchableOpacity 
        style={[styles.dayItem, isSelected && styles.selectedDayItem]} 
        onPress={() => onDateSelect(item)}
      >
        <Text style={[styles.dayText, isSelected && styles.selectedDayText]}>{dayName}</Text>
        <Text style={[styles.dayNumber, isSelected && styles.selectedDayNumber]}>{dayNum}</Text>
        {events.some(e => new Date(e.startDate).toDateString() === item.toDateString()) && (
          <View style={[styles.dot, isSelected && styles.selectedDot]} />
        )}
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* Weekly Slider */}
      <View style={styles.header}>
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={weekDays}
          renderItem={renderDay}
          keyExtractor={(item) => item.toISOString()}
          contentContainerStyle={styles.weekList}
        />
      </View>

      {/* Events List */}
      <FlatList
        data={filteredEvents}
        keyExtractor={item => item.id}
        contentContainerStyle={styles.eventsContent}
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>No events scheduled for this day</Text>
          </View>
        }
        renderItem={({ item }) => (
          <View style={styles.eventCard}>
            <View style={styles.timeColumn}>
              <Text style={styles.timeText}>
                {new Date(item.startDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </Text>
              <View style={styles.timeLine} />
            </View>
            <View style={styles.eventDetails}>
              <Text style={styles.eventTitleText}>{item.title}</Text>
              <Text style={styles.durationText}>
                {Math.round((new Date(item.endDate).getTime() - new Date(item.startDate).getTime()) / 60000)} mins
              </Text>
            </View>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8F9FA',
  },
  header: {
    backgroundColor: '#FFFFFF',
    paddingVertical: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#EEEEEE',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
  },
  weekList: {
    paddingHorizontal: 10,
  },
  dayItem: {
    width: DAY_WIDTH - 10,
    height: 70,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 5,
    borderRadius: 12,
  },
  selectedDayItem: {
    backgroundColor: '#007AFF',
  },
  dayText: {
    fontSize: 12,
    color: '#8E8E93',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  selectedDayText: {
    color: '#FFFFFF',
    opacity: 0.8,
  },
  dayNumber: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1C1C1E',
  },
  selectedDayNumber: {
    color: '#FFFFFF',
  },
  dot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#007AFF',
    marginTop: 4,
  },
  selectedDot: {
    backgroundColor: '#FFFFFF',
  },
  eventsContent: {
    padding: 20,
  },
  eventCard: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  timeColumn: {
    width: 70,
    alignItems: 'center',
    paddingRight: 10,
    borderRightWidth: 1,
    borderRightColor: '#F2F2F7',
  },
  timeText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#007AFF',
  },
  timeLine: {
    flex: 1,
    width: 2,
    backgroundColor: '#E5E5EA',
    marginTop: 8,
    borderRadius: 1,
  },
  eventDetails: {
    flex: 1,
    paddingLeft: 15,
    justifyContent: 'center',
  },
  eventTitleText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1C1C1E',
    marginBottom: 4,
  },
  durationText: {
    fontSize: 13,
    color: '#8E8E93',
  },
  emptyState: {
    marginTop: 100,
    alignItems: 'center',
  },
  emptyText: {
    color: '#C7C7CC',
    fontSize: 16,
  },
});