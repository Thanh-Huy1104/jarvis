import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  StyleSheet, 
  FlatList, 
  TouchableOpacity, 
  Dimensions, 
  Platform,
  LayoutAnimation,
  UIManager,
  View,
  Text,
  StatusBar,
  Animated,
  PanResponder
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getCalendarEvents } from '../../services/api';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const { width, height: SCREEN_HEIGHT } = Dimensions.get('window');
const DAY_WIDTH = width / 7.5;
const FOCUSED_EVENT_HEIGHT = SCREEN_HEIGHT * 0.65;
const COLLAPSED_EVENT_HEIGHT = 200;

export default function CalendarScreen() {
  const [events, setEvents] = useState<any[]>([]);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);
  const dragY = useRef(new Animated.Value(0)).current;

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => !expandedEvent,
      onMoveShouldSetPanResponder: () => !expandedEvent,
      onPanResponderMove: (_, gestureState) => {
        if (gestureState.dy > 0) {
          dragY.setValue(gestureState.dy);
        }
      },
      onPanResponderRelease: () => {
        Animated.spring(dragY, {
          toValue: 0,
          friction: 8,
          tension: 40,
          useNativeDriver: false,
        }).start();
      },
    })
  ).current;

  // Generate 21 days (last week, current week, next week)
  const weekDays = useMemo(() => {
    const days = [];
    const start = new Date();
    start.setDate(start.getDate() - 7); 
    for (let i = 0; i < 21; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      days.push(d);
    }
    return days;
  }, []);

  useEffect(() => {
    fetchEvents();
    // Scroll to "today" (index 7)
    setTimeout(() => {
      flatListRef.current?.scrollToIndex({ index: 7, animated: false, viewPosition: 0.5 });
    }, 100);
  }, []);

  const fetchEvents = async () => {
    try {
      setLoading(true);
      const fetchedData = await getCalendarEvents();
      if (fetchedData && fetchedData.events) {
        const transformed = fetchedData.events.map((event: any) => {
          const startDate = new Date(event.event_datetime);
          return {
            id: event.id,
            title: event.title,
            startDate: startDate.toISOString(),
            endDate: new Date(startDate.getTime() + event.duration_minutes * 60000).toISOString(),
          };
        });
        setEvents(transformed);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const filteredEvents = useMemo(() => {
    return events.filter(event => 
      new Date(event.startDate).toDateString() === selectedDate.toDateString()
    );
  }, [events, selectedDate]);

  const onDateSelect = (date: Date) => {
    LayoutAnimation.configureNext({
      duration: 400,
      create: { type: 'easeInEaseOut', property: 'opacity' },
      update: { type: 'spring', springDamping: 0.8 },
      delete: { type: 'easeInEaseOut', property: 'opacity' },
    });
    setSelectedDate(date);
    setExpandedEvent(null);
  };

  const handleEventPress = (eventId: string) => {
    const isExpanding = expandedEvent !== eventId;
    
    LayoutAnimation.configureNext({
      duration: 600,
      create: { type: 'easeInEaseOut', property: 'opacity' },
      update: { type: 'spring', springDamping: 0.8 },
      delete: { type: 'easeInEaseOut', property: 'opacity' },
    });

    setExpandedEvent(isExpanding ? eventId : null);
  };

  const cardColors = ['#1C1C1E', '#007AFF', '#5856D6', '#FF9500', '#32D74B'];

  const renderDay = ({ item }: { item: Date }) => {
    const isSelected = item.toDateString() === selectedDate.toDateString();
    const isToday = item.toDateString() === new Date().toDateString();
    
    return (
      <TouchableOpacity 
        style={[styles.dayItem, isSelected && styles.selectedDayItem]} 
        onPress={() => onDateSelect(item)}
      >
        <Text style={[styles.dayText, isSelected && styles.selectedDayText]}>
          {item.toLocaleDateString('en-US', { weekday: 'short' }).charAt(0)}
        </Text>
        <Text style={[styles.dayNumber, isSelected && styles.selectedDayNumber]}>
          {item.getDate()}
        </Text>
        {isToday && !isSelected && <View style={styles.todayDot} />}
      </TouchableOpacity>
    );
  };

  const renderEvent = (event: any, index: number) => {
    const isExpanded = expandedEvent === event.id;
    const anyExpanded = expandedEvent !== null;
    const bgColor = cardColors[index % cardColors.length];

    let topPosition = index * 120;
    let opacity = 1;
    let scale = 1 - (filteredEvents.length - 1 - index) * 0.025;
    let cardHeight = COLLAPSED_EVENT_HEIGHT;

    if (anyExpanded) {
      if (isExpanded) {
        topPosition = 0;
        scale = 1;
        cardHeight = FOCUSED_EVENT_HEIGHT;
      } else {
        const unexpandedEvents = filteredEvents.filter(e => e.id !== expandedEvent);
        const relIdx = unexpandedEvents.findIndex(e => e.id === event.id);
        
        topPosition = SCREEN_HEIGHT * 0.7 + (relIdx * 40);
        scale = 0.94 + (relIdx * 0.015);
        cardHeight = COLLAPSED_EVENT_HEIGHT;
      }
    }

    const translateY = dragY.interpolate({
      inputRange: [0, 400],
      outputRange: [0, index * 50],
      extrapolate: 'clamp',
    });

    const startTime = new Date(event.startDate);
    const endTime = new Date(event.endDate);
    const duration = Math.round((endTime.getTime() - startTime.getTime()) / 60000);

    return (
      <Animated.View
        key={event.id}
        style={[
          styles.eventCardContainer,
          { 
            top: topPosition, 
            zIndex: isExpanded ? 100 : index,
            opacity,
            height: cardHeight,
            transform: [
              { scale }, 
              { translateY: anyExpanded ? 0 : translateY }
            ]
          }
        ]}
      >
        <TouchableOpacity
          activeOpacity={1}
          onPress={() => handleEventPress(event.id)}
          style={[styles.eventCard, { backgroundColor: bgColor }]}
        >
          <View style={styles.eventHeader}>
            <View style={styles.eventIconBox}>
              <Ionicons name="calendar" size={20} color="#FFFFFF" />
            </View>
            <View style={styles.eventTitleWrapper}>
              <Text style={styles.eventTitle}>{event.title}</Text>
              <Text style={styles.eventTime}>
                {startTime.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })}
              </Text>
            </View>
            {isExpanded && (
              <TouchableOpacity onPress={() => handleEventPress(event.id)}>
                <Ionicons name="chevron-down" size={24} color="rgba(255,255,255,0.4)" />
              </TouchableOpacity>
            )}
          </View>

          {isExpanded ? (
            <View style={styles.eventDetailsExpanded}>
              <View style={styles.detailRow}>
                <Ionicons name="time-outline" size={18} color="rgba(255,255,255,0.7)" />
                <Text style={styles.detailText}>{duration} minutes</Text>
              </View>
              <View style={styles.detailRow}>
                <Ionicons name="calendar-outline" size={18} color="rgba(255,255,255,0.7)" />
                <Text style={styles.detailText}>
                  {startTime.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                </Text>
              </View>
              <View style={styles.detailRow}>
                <Ionicons name="arrow-forward" size={18} color="rgba(255,255,255,0.7)" />
                <Text style={styles.detailText}>
                  {startTime.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })} - {endTime.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })}
                </Text>
              </View>
            </View>
          ) : (
            <View style={styles.eventDetailsPreview}>
              <View style={styles.durationBadge}>
                <Ionicons name="time-outline" size={14} color="rgba(255,255,255,0.6)" />
                <Text style={styles.durationText}>{duration} mins</Text>
              </View>
            </View>
          )}

          {!anyExpanded && (
            <View style={styles.peekIndicator}>
              <Ionicons name="chevron-forward" size={16} color="rgba(255,255,255,0.15)" />
            </View>
          )}
        </TouchableOpacity>
      </Animated.View>
    );
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" />
      <View style={styles.container}>
        {!expandedEvent && (
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>Calendar</Text>
              <Text style={styles.subtitle}>
                {selectedDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              </Text>
            </View>
            <TouchableOpacity style={styles.headerButton}>
              <Ionicons name="add" size={28} color="#FFFFFF" />
            </TouchableOpacity>
          </View>
        )}

        <View style={styles.weekScrollContainer}>
          <FlatList
            ref={flatListRef}
            horizontal
            showsHorizontalScrollIndicator={false}
            data={weekDays}
            renderItem={renderDay}
            keyExtractor={(item) => item.toISOString()}
            contentContainerStyle={styles.weekList}
            getItemLayout={(_, index) => ({ length: DAY_WIDTH, offset: DAY_WIDTH * index, index })}
          />
        </View>

        <View style={styles.eventsStackArea} {...panResponder.panHandlers}>
          {loading ? (
            <View style={styles.loadingContainer}>
              <Ionicons name="calendar-outline" size={48} color="#8E8E93" />
              <Text style={styles.loadingText}>Loading events...</Text>
            </View>
          ) : filteredEvents.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="calendar-outline" size={64} color="#3A3A3C" />
              <Text style={styles.emptyText}>No events today</Text>
              <Text style={styles.emptySubtext}>Tap + to create one</Text>
            </View>
          ) : (
            <View style={styles.eventsWrapper}>
              {filteredEvents.map((event, index) => renderEvent(event, index))}
            </View>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000000',
  },
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    paddingHorizontal: 24,
    paddingTop: 10,
    paddingBottom: 20,
  },
  title: {
    fontSize: 34,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 14,
    color: '#8E8E93',
    fontWeight: '600',
    marginTop: 2,
  },
  headerButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#1C1C1E',
    justifyContent: 'center',
    alignItems: 'center',
  },
  weekScrollContainer: {
    backgroundColor: '#000000',
    paddingVertical: 15,
    borderBottomWidth: 0.5,
    borderBottomColor: '#1C1C1E',
  },
  weekList: {
    paddingHorizontal: 10,
  },
  dayItem: {
    width: DAY_WIDTH - 8,
    height: 65,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 4,
    borderRadius: 16,
    backgroundColor: '#1C1C1E',
  },
  selectedDayItem: {
    backgroundColor: '#007AFF',
  },
  dayText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#8E8E93',
    marginBottom: 4,
  },
  selectedDayText: {
    color: 'rgba(255,255,255,0.7)',
  },
  dayNumber: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  selectedDayNumber: {
    color: '#FFF',
  },
  todayDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#007AFF',
    marginTop: 4,
  },
  eventsStackArea: {
    flex: 1,
    paddingHorizontal: 12,
    paddingTop: 20,
    position: 'relative',
  },
  eventsWrapper: {
    flex: 1,
    position: 'relative',
  },
  eventCardContainer: {
    position: 'absolute',
    left: 0,
    right: 0,
  },
  eventCard: {
    borderRadius: 32,
    padding: 24,
    height: '100%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -10 },
    shadowOpacity: 0.6,
    shadowRadius: 15,
    elevation: 20,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.15)',
    overflow: 'hidden',
  },
  eventHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 15,
  },
  eventIconBox: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  eventTitleWrapper: {
    flex: 1,
  },
  eventTitle: {
    fontSize: 19,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  eventTime: {
    fontSize: 13,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.5)',
    marginTop: 2,
  },
  eventDetailsPreview: {
    marginTop: 8,
  },
  durationBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.1)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
    alignSelf: 'flex-start',
  },
  durationText: {
    color: 'rgba(255,255,255,0.6)',
    fontSize: 13,
    fontWeight: '600',
    marginLeft: 6,
  },
  eventDetailsExpanded: {
    marginTop: 20,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.06)',
    padding: 16,
    borderRadius: 16,
    marginBottom: 10,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  detailText: {
    color: '#FFFFFF',
    fontSize: 15,
    marginLeft: 12,
    flex: 1,
  },
  peekIndicator: {
    position: 'absolute',
    bottom: 20,
    right: 20,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#8E8E93',
    fontSize: 16,
    marginTop: 12,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingBottom: 100,
  },
  emptyText: {
    color: '#8E8E93',
    fontSize: 20,
    fontWeight: '600',
    marginTop: 16,
  },
  emptySubtext: {
    color: '#3A3A3C',
    fontSize: 14,
    marginTop: 8,
  },
});