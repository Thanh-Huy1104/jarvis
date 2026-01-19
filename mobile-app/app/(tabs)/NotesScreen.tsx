import React, { useState, useEffect } from 'react';
import { 
  StyleSheet, 
  FlatList, 
  TouchableOpacity, 
  ActivityIndicator, 
  LayoutAnimation,
  Platform,
  UIManager
} from 'react-native';
import { Text, View } from '@/components/Themed';
import { getSections, getNotesBySection } from '../../services/api';
import { Ionicons } from '@expo/vector-icons';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface Note {
  id: string;
  content: string;
}

interface Section {
  id: string;
  name: string;
  notes_preview: Note[];
  notes?: Note[];
}

export default function NotesScreen() {
  const [sections, setSections] = useState<Section[]>([]);
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSections();
  }, []);

  const fetchSections = async () => {
    try {
      setLoading(true);
      const data = await getSections();
      if (data?.sections) setSections(data.sections);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = async (sectionId: string) => {
    const isExpanding = expandedSection !== sectionId;
    
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpandedSection(isExpanding ? sectionId : null);

    if (isExpanding) {
      const section = sections.find(s => s.id === sectionId);
      if (section && !section.notes) {
        try {
          const notesData = await getNotesBySection(sectionId);
          if (notesData?.notes) {
            setSections(prev =>
              prev.map(s => s.id === sectionId ? { ...s, notes: notesData.notes } : s)
            );
          }
        } catch (err) {
          console.error(err);
        }
      }
    }
  };

  const renderSection = ({ item }: { item: Section }) => {
    const isExpanded = expandedSection === item.id;
    const notes = isExpanded ? (item.notes || item.notes_preview) : item.notes_preview;

    return (
      <View style={[styles.card, isExpanded && styles.expandedCard]}>
        <TouchableOpacity 
          activeOpacity={0.7} 
          onPress={() => toggleSection(item.id)}
          style={styles.cardHeader}
        >
          <View style={styles.titleRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="folder-outline" size={20} color="#007AFF" />
            </View>
            <Text style={styles.sectionTitle}>{item.name}</Text>
          </View>
          <Ionicons 
            name={isExpanded ? "chevron-up" : "chevron-down"} 
            size={20} 
            color="#C7C7CC" 
          />
        </TouchableOpacity>

        {isExpanded && !item.notes && (
          <ActivityIndicator style={{ marginVertical: 10 }} color="#007AFF" />
        )}

        <View style={styles.notesList}>
          {notes?.map((note, index) => (
            <View key={note.id} style={[styles.noteItem, index === notes.length - 1 && styles.lastNote]}>
              <View style={styles.noteBullet} />
              <Text style={styles.noteText}>{note.content}</Text>
            </View>
          ))}
          {!isExpanded && item.notes_preview.length > 0 && (
            <Text style={styles.moreText}>+ View all notes</Text>
          )}
        </View>
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={sections}
        renderItem={renderSection}
        keyExtractor={s => s.id}
        contentContainerStyle={styles.listContainer}
        ListEmptyComponent={
          <View style={styles.centered}>
            <Text style={styles.emptyText}>Your notebook is empty</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F8F9FA' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  listContainer: { padding: 16 },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    marginBottom: 16,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 3,
  },
  expandedCard: {
    borderColor: '#007AFF',
    borderWidth: 1,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  titleRow: { flexDirection: 'row', alignItems: 'center' },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: '#F2F2F7',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: '#1C1C1E' },
  notesList: { marginTop: 4 },
  noteItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F2F2F7',
  },
  lastNote: { borderBottomWidth: 0 },
  noteBullet: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#007AFF',
    marginTop: 8,
    marginRight: 12,
  },
  noteText: { flex: 1, fontSize: 15, color: '#3A3A3C', lineHeight: 20 },
  moreText: {
    fontSize: 13,
    color: '#007AFF',
    fontWeight: '600',
    marginTop: 8,
    textAlign: 'center',
  },
  emptyText: { color: '#8E8E93', fontSize: 16 },
});