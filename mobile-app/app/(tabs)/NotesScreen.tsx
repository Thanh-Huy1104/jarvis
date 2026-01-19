import React, { useState, useEffect, useRef } from 'react';
import { 
  StyleSheet, 
  View, 
  Text, 
  TouchableOpacity, 
  ScrollView, 
  Dimensions, 
  LayoutAnimation, 
  Platform, 
  UIManager,
  ActivityIndicator,
  StatusBar,
  Animated,
  PanResponder,
  Modal,
  TextInput,
  KeyboardAvoidingView
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getSections, getNotesBySection, createSection, createNote } from '../../services/api';

// Enable LayoutAnimation for Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const { height: SCREEN_HEIGHT } = Dimensions.get('window');
const FOCUSED_CARD_HEIGHT = SCREEN_HEIGHT * 0.6;
const COLLAPSED_CARD_HEIGHT = 220; 
const BOTTOM_STACK_START = SCREEN_HEIGHT * 0.68;
const BASE_CARD_SPACING = 135; 

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
  const [showSectionModal, setShowSectionModal] = useState(false);
  const [showNoteModal, setShowNoteModal] = useState(false);
  const [newSectionName, setNewSectionName] = useState('');
  const [newNoteContent, setNewNoteContent] = useState('');
  const [selectedSectionForNote, setSelectedSectionForNote] = useState<string | null>(null);
  
  // Animation value for fanning the stack when dragging
  const dragY = useRef(new Animated.Value(0)).current;

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => !expandedSection,
      onMoveShouldSetPanResponder: () => !expandedSection,
      onPanResponderMove: (_, gestureState) => {
        if (gestureState.dy > 0) {
          dragY.setValue(gestureState.dy);
        }
      },
      onPanResponderRelease: (_, gestureState) => {
        Animated.spring(dragY, {
          toValue: 0,
          friction: 8,
          tension: 40,
          useNativeDriver: false,
        }).start();
      },
    })
  ).current;

  useEffect(() => {
    fetchSections();
  }, []);

  const fetchSections = async () => {
    try {
      setLoading(true);
      const data = await getSections();
      if (data?.sections) {
        setSections(data.sections);
      }
    } catch (err) {
      console.error('Error fetching sections:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCardPress = async (sectionId: string) => {
    const isExpanding = expandedSection !== sectionId;
    
    // Apple-style bouncy transition
    LayoutAnimation.configureNext({
      duration: 600,
      create: { type: 'easeInEaseOut', property: 'opacity' },
      update: { type: 'spring', springDamping: 0.8 },
      delete: { type: 'easeInEaseOut', property: 'opacity' },
    });

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
          console.error('Error fetching notes:', err);
        }
      }
    }
  };

  const handleCreateSection = async () => {
    if (!newSectionName.trim()) return;
    
    try {
      await createSection(newSectionName.trim());
      setNewSectionName('');
      setShowSectionModal(false);
      await fetchSections();
    } catch (err) {
      console.error('Error creating section:', err);
    }
  };

  const handleOpenNoteModal = (sectionId: string) => {
    setSelectedSectionForNote(sectionId);
    setShowNoteModal(true);
  };

  const handleCreateNote = async () => {
    if (!newNoteContent.trim() || !selectedSectionForNote) return;
    
    try {
      await createNote(parseInt(selectedSectionForNote), newNoteContent.trim());
      setNewNoteContent('');
      setShowNoteModal(false);
      
      // Refresh the notes for this section
      const notesData = await getNotesBySection(selectedSectionForNote);
      if (notesData?.notes) {
        setSections(prev =>
          prev.map(s => s.id === selectedSectionForNote ? { ...s, notes: notesData.notes } : s)
        );
      }
    } catch (err) {
      console.error('Error creating note:', err);
    }
  };

  const cardColors = ['#1C1C1E', '#007AFF', '#5856D6', '#FF9500', '#32D74B'];

  const renderCard = (section: Section, index: number) => {
    const isExpanded = expandedSection === section.id;
    const anyExpanded = expandedSection !== null;
    const bgColor = cardColors[index % cardColors.length];

    // Card Stack Positioning Logic
    let topPosition = index * BASE_CARD_SPACING;
    let opacity = 1;
    let scale = 1 - (sections.length - 1 - index) * 0.025;
    let cardHeight = COLLAPSED_CARD_HEIGHT;

    if (anyExpanded) {
      if (isExpanded) {
        topPosition = 15;
        scale = 1;
        cardHeight = FOCUSED_CARD_HEIGHT;
      } else {
        const unexpandedSections = sections.filter(s => s.id !== expandedSection);
        const relIdx = unexpandedSections.findIndex(s => s.id === section.id);
        
        topPosition = BOTTOM_STACK_START + (relIdx * 50);
        scale = 0.94 + (relIdx * 0.015);
        opacity = 1;
        cardHeight = COLLAPSED_CARD_HEIGHT;
      }
    }

    const translateY = dragY.interpolate({
      inputRange: [0, 400],
      outputRange: [0, index * 60],
      extrapolate: 'clamp',
    });

    const displayNotes = isExpanded 
      ? (section.notes || section.notes_preview) 
      : section.notes_preview.slice(0, 3);

    return (
      <Animated.View
        key={section.id}
        style={[
          styles.cardContainer,
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
          onPress={() => handleCardPress(section.id)}
          style={[styles.card, { backgroundColor: bgColor }]}
        >
          {/* Card Header */}
          <View style={styles.cardHeader}>
            <View style={styles.iconBox}>
              <Ionicons name="journal" size={20} color="#FFFFFF" />
            </View>
            <View style={styles.titleWrapper}>
              <Text style={styles.cardTitle}>{section.name}</Text>
              <Text style={styles.cardSubtitle}>
                {section.notes?.length || section.notes_preview.length} ITEMS
              </Text>
            </View>
            {isExpanded && (
              <TouchableOpacity onPress={() => handleCardPress(section.id)}>
                <Ionicons name="chevron-down" size={24} color="rgba(255,255,255,0.4)" />
              </TouchableOpacity>
            )}
          </View>

          {/* Content Area */}
          <View style={styles.contentWrapper}>
            {isExpanded ? (
              <View style={styles.scrollContainer}>
                <ScrollView 
                  style={styles.notesList} 
                  showsVerticalScrollIndicator={false}
                  contentContainerStyle={styles.scrollContent}
                >
                  {displayNotes.map((note) => (
                    <View key={note.id} style={styles.noteItem}>
                      <View style={styles.noteBullet} />
                      <Text style={styles.noteText}>{note.content}</Text>
                    </View>
                  ))}
                </ScrollView>
                
                {/* Absolute button at bottom of focused card */}
                <View style={styles.absoluteAddWrapper}>
                   <TouchableOpacity style={styles.addButton} onPress={() => handleOpenNoteModal(section.id)}>
                    <Ionicons name="add" size={18} color="#000" />
                    <Text style={styles.addButtonText}>New Note</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : (
              <View style={styles.previewList}>
                {displayNotes.map((note) => (
                  <View key={note.id} style={styles.previewItem}>
                    <View style={styles.previewBullet} />
                    <Text style={styles.previewText} numberOfLines={1}>{note.content}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>

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
        {!expandedSection && (
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>Notes</Text>
              <Text style={styles.subtitle}>Collections</Text>
            </View>
            <TouchableOpacity style={styles.headerButton} onPress={() => setShowSectionModal(true)}>
              <Ionicons name="add" size={28} color="#FFFFFF" />
            </TouchableOpacity>
          </View>
        )}

        <View style={styles.stackArea} {...panResponder.panHandlers}>
          {loading ? (
            <ActivityIndicator size="large" color="#007AFF" style={styles.loader} />
          ) : (
            <View style={styles.cardsWrapper}>
              {sections.map((section, index) => renderCard(section, index))}
            </View>
          )}
        </View>
      </View>

      {/* Create Section Modal */}
      <Modal
        visible={showSectionModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowSectionModal(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <TouchableOpacity 
            style={styles.modalBackdrop} 
            activeOpacity={1}
            onPress={() => setShowSectionModal(false)}
          />
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>New Collection</Text>
              <TouchableOpacity onPress={() => setShowSectionModal(false)}>
                <Ionicons name="close-circle" size={28} color="#8E8E93" />
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.modalInput}
              placeholder="Collection name"
              placeholderTextColor="#6E6E73"
              value={newSectionName}
              onChangeText={setNewSectionName}
              autoFocus
              returnKeyType="done"
              onSubmitEditing={handleCreateSection}
            />
            <TouchableOpacity 
              style={[styles.modalButton, !newSectionName.trim() && styles.modalButtonDisabled]}
              onPress={handleCreateSection}
              disabled={!newSectionName.trim()}
            >
              <Text style={styles.modalButtonText}>Create Collection</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Create Note Modal */}
      <Modal
        visible={showNoteModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowNoteModal(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <TouchableOpacity 
            style={styles.modalBackdrop} 
            activeOpacity={1}
            onPress={() => setShowNoteModal(false)}
          />
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>New Note</Text>
              <TouchableOpacity onPress={() => setShowNoteModal(false)}>
                <Ionicons name="close-circle" size={28} color="#8E8E93" />
              </TouchableOpacity>
            </View>
            <TextInput
              style={[styles.modalInput, styles.modalInputMultiline]}
              placeholder="Write your note..."
              placeholderTextColor="#6E6E73"
              value={newNoteContent}
              onChangeText={setNewNoteContent}
              multiline
              autoFocus
              textAlignVertical="top"
            />
            <TouchableOpacity 
              style={[styles.modalButton, !newNoteContent.trim() && styles.modalButtonDisabled]}
              onPress={handleCreateNote}
              disabled={!newNoteContent.trim()}
            >
              <Text style={styles.modalButtonText}>Add Note</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
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
    paddingBottom: 25,
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
  stackArea: {
    flex: 1,
    paddingHorizontal: 12,
    position: 'relative',
  },
  loader: {
    marginTop: 50,
  },
  cardsWrapper: {
    flex: 1,
    position: 'relative',
  },
  cardContainer: {
    position: 'absolute',
    left: 0,
    right: 0,
  },
  card: {
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
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 15,
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  titleWrapper: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 19,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  cardSubtitle: {
    fontSize: 9,
    fontWeight: '800',
    color: 'rgba(255,255,255,0.4)',
    letterSpacing: 1.2,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  contentWrapper: {
    flex: 1,
  },
  previewList: {
    opacity: 0.8,
    marginTop: 5,
  },
  previewItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  previewBullet: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.3)',
    marginRight: 10,
  },
  previewText: {
    color: 'rgba(255,255,255,0.6)',
    fontSize: 14,
    flex: 1,
  },
  scrollContainer: {
    flex: 1,
    position: 'relative',
  },
  notesList: {
    flex: 1,
    marginTop: 5,
  },
  scrollContent: {
    paddingBottom: 90, // Clear the absolute addButton
  },
  noteItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.06)',
    padding: 18,
    borderRadius: 20,
    marginBottom: 12,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  noteBullet: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: '#FFFFFF',
    marginTop: 8,
    marginRight: 12,
    opacity: 0.3,
  },
  noteText: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 20,
  },
  absoluteAddWrapper: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingTop: 15,
  },
  addButton: {
    backgroundColor: '#FFFFFF',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    borderRadius: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 8,
  },
  addButtonText: {
    color: '#000000',
    fontWeight: '700',
    fontSize: 15,
    marginLeft: 6,
  },
  peekIndicator: {
    position: 'absolute',
    bottom: 20,
    right: 20,
  },
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalBackdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.7)',
  },
  modalContent: {
    backgroundColor: '#1C1C1E',
    borderRadius: 28,
    padding: 24,
    width: '85%',
    maxWidth: 400,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.1)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 20 },
    shadowOpacity: 0.5,
    shadowRadius: 30,
    elevation: 24,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  modalInput: {
    backgroundColor: '#2C2C2E',
    borderRadius: 16,
    padding: 16,
    fontSize: 16,
    color: '#FFFFFF',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.1)',
    marginBottom: 20,
  },
  modalInputMultiline: {
    height: 120,
    paddingTop: 16,
  },
  modalButton: {
    backgroundColor: '#007AFF',
    paddingVertical: 16,
    borderRadius: 16,
    alignItems: 'center',
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  modalButtonDisabled: {
    backgroundColor: '#3A3A3C',
    shadowOpacity: 0,
  },
  modalButtonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
});