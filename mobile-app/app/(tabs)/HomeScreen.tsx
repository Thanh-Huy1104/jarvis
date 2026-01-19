import React, { useState, useRef } from 'react';
import {
  StyleSheet,
  TextInput,
  FlatList,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  View,
  Text,
  StatusBar
} from 'react-native';
import { sendMessage, createSection } from '../../services/api';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'bot';
  needsClarification?: boolean;
  clarificationData?: any;
}

export default function HomeScreen() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [pendingClarification, setPendingClarification] = useState<any>(null);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const handleSendMessage = async () => {
    if (message.trim() === '') return;

    const userMessage: Message = { id: Date.now().toString(), text: message, sender: 'user' };
    setMessages(prev => [...prev, userMessage]);
    setMessage('');

    try {
      const messageWithContext = activeSection
        ? `Add note to ${activeSection}: ${message}`
        : message;

      const botResponse = await sendMessage(messageWithContext);

      const isYesNo = botResponse.result?.needs_section_creation;
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: botResponse.result?.clarification_question || botResponse.response,
        sender: 'bot',
        needsClarification: isYesNo,
        clarificationData: botResponse.result
      };

      setMessages(prev => [...prev, botMessage]);
      if (isYesNo) setPendingClarification(botResponse.result);
      if (botResponse.result?.success) setActiveSection(null);

    } catch (error) {
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`,
        text: 'Connection issue. Try again.',
        sender: 'bot'
      }]);
    }
  };

  const handleYesNo = async (response: 'yes' | 'no') => {
    if (!pendingClarification) return;

    const userMsg: Message = { id: Date.now().toString(), text: response.toUpperCase(), sender: 'user' };
    setMessages(prev => [...prev, userMsg]);

    if (response === 'yes' && pendingClarification.needs_section_creation) {
      try {
        await createSection(pendingClarification.section_name);
        setActiveSection(pendingClarification.section_name);
        setMessages(prev => [...prev, {
          id: `bot-succ-${Date.now()}`,
          text: `Done! Created "${pendingClarification.section_name}". What's the note?`,
          sender: 'bot'
        }]);
      } catch (err) {
        setMessages(prev => [...prev, {
          id: `bot-err-${Date.now()}`,
          text: 'Could not create section.',
          sender: 'bot'
        }]);
      }
    } else {
      setMessages(prev => [...prev, {
        id: `bot-can-${Date.now()}`,
        text: 'No problem. Anything else?',
        sender: 'bot'
      }]);
    }
    setPendingClarification(null);
  };

  const renderMessage = ({ item }: { item: Message }) => {
    const isUser = item.sender === 'user';
    return (
      <View style={[styles.messageRow, isUser ? styles.userRow : styles.botRow]}>
        <View style={[styles.bubble, isUser ? styles.userBubble : styles.botBubble]}>
          <Text style={[styles.messageText, isUser ? styles.userText : styles.botText]}>{item.text}</Text>
          {item.needsClarification && (
            <View style={styles.actionContainer}>
              <TouchableOpacity style={styles.actionButton} onPress={() => handleYesNo('yes')}>
                <Text style={styles.actionButtonText}>Yes, create it</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.actionButton, styles.cancelButton]} onPress={() => handleYesNo('no')}>
                <Text style={styles.cancelButtonText}>No</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" />
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Chat</Text>
          <Text style={styles.subtitle}>Assistant</Text>
        </View>

        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.keyboardView}
          keyboardVerticalOffset={90}
        >
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={item => item.id}
            renderItem={renderMessage}
            contentContainerStyle={styles.listContent}
            onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
            ListEmptyComponent={
              <View style={styles.emptyState}>
                <Ionicons name="chatbubbles-outline" size={64} color="#3A3A3C" />
                <Text style={styles.emptyText}>Start a conversation</Text>
                <Text style={styles.emptySubtext}>Ask me anything or create notes</Text>
              </View>
            }
          />

          <View style={styles.inputArea}>
            {activeSection && (
              <View style={styles.contextBadge}>
                <Text style={styles.contextText}>Target: {activeSection}</Text>
                <TouchableOpacity onPress={() => setActiveSection(null)}>
                  <Ionicons name="close-circle" size={16} color="#007AFF" />
                </TouchableOpacity>
              </View>
            )}
            <View style={styles.inputWrapper}>
              <TextInput
                style={styles.input}
                value={message}
                onChangeText={setMessage}
                placeholder="Write a note or ask a question..."
                placeholderTextColor="#6E6E73"
                multiline
              />
              <TouchableOpacity
                style={[styles.sendButton, !message.trim() && styles.sendButtonDisabled]}
                onPress={handleSendMessage}
                disabled={!message.trim()}
              >
                <Ionicons name="arrow-up" size={24} color="white" />
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
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
  keyboardView: {
    flex: 1,
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  messageRow: {
    marginBottom: 12,
    flexDirection: 'row',
    width: '100%',
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  botRow: {
    justifyContent: 'flex-start',
  },
  bubble: {
    maxWidth: '80%',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 3,
  },
  userBubble: {
    backgroundColor: '#007AFF',
    borderBottomRightRadius: 4,
  },
  botBubble: {
    backgroundColor: '#1C1C1E',
    borderBottomLeftRadius: 4,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  messageText: {
    fontSize: 16,
    lineHeight: 22,
  },
  userText: {
    color: '#FFFFFF',
  },
  botText: {
    color: '#FFFFFF',
  },
  inputArea: {
    padding: 12,
    backgroundColor: '#000000',
    borderTopWidth: 0.5,
    borderTopColor: '#1C1C1E',
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: '#1C1C1E',
    borderRadius: 24,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  input: {
    flex: 1,
    fontSize: 16,
    maxHeight: 100,
    paddingTop: 8,
    paddingBottom: 8,
    color: '#FFFFFF',
  },
  sendButton: {
    backgroundColor: '#007AFF',
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 8,
  },
  sendButtonDisabled: {
    backgroundColor: '#3A3A3C',
  },
  contextBadge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(0, 122, 255, 0.2)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
    marginBottom: 8,
    marginLeft: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 0.5,
    borderColor: 'rgba(0, 122, 255, 0.3)',
  },
  contextText: {
    fontSize: 12,
    color: '#007AFF',
    fontWeight: '600',
  },
  actionContainer: {
    marginTop: 12,
    gap: 8,
  },
  actionButton: {
    backgroundColor: 'rgba(255,255,255,0.1)',
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  actionButtonText: {
    color: '#007AFF',
    fontWeight: '600',
    fontSize: 15,
  },
  cancelButton: {
    backgroundColor: 'transparent',
    borderColor: 'rgba(255,59,48,0.3)',
  },
  cancelButtonText: {
    color: '#FF3B30',
    fontWeight: '600',
    fontSize: 15,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
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