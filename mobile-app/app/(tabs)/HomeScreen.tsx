import React, { useState, useRef } from 'react';
import { 
  StyleSheet, 
  TextInput, 
  FlatList, 
  TouchableOpacity, 
  KeyboardAvoidingView, 
  Platform,
  View as DefaultView // Import standard View for layout wrappers
} from 'react-native';
import { Text, View } from '@/components/Themed';
import { sendMessage, createSection } from '../../services/api';
import { Ionicons } from '@expo/vector-icons';

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
      <DefaultView style={[styles.messageRow, isUser ? styles.userRow : styles.botRow]}>
        <View style={[styles.bubble, isUser ? styles.userBubble : styles.botBubble]}>
          <Text style={[styles.messageText, isUser ? styles.userText : styles.botText]}>{item.text}</Text>
          {item.needsClarification && (
            <DefaultView style={styles.actionContainer}>
              <TouchableOpacity style={styles.actionButton} onPress={() => handleYesNo('yes')}>
                <Text style={styles.actionButtonText}>Yes, create it</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.actionButton, styles.cancelButton]} onPress={() => handleYesNo('no')}>
                <Text style={styles.cancelButtonText}>No</Text>
              </TouchableOpacity>
            </DefaultView>
          )}
        </View>
      </DefaultView>
    );
  };

  return (
    <KeyboardAvoidingView 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'} 
      style={styles.container}
      keyboardVerticalOffset={90}
    >
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={item => item.id}
        renderItem={renderMessage}
        contentContainerStyle={styles.listContent}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
      />

      <View style={styles.inputArea}>
        {activeSection && (
          <DefaultView style={styles.contextBadge}>
            <Text style={styles.contextText}>Target: {activeSection}</Text>
          </DefaultView>
        )}
        <DefaultView style={styles.inputWrapper}>
          <TextInput
            style={styles.input}
            value={message}
            onChangeText={setMessage}
            placeholder="Write a note or ask a question..."
            placeholderTextColor="#999"
            multiline
          />
          <TouchableOpacity 
            style={[styles.sendButton, !message.trim() && styles.sendButtonDisabled]} 
            onPress={handleSendMessage}
            disabled={!message.trim()}
          >
            <Ionicons name="arrow-up" size={24} color="white" />
          </TouchableOpacity>
        </DefaultView>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F2F2F7' },
  listContent: { padding: 16, paddingBottom: 32 },
  messageRow: { 
    marginBottom: 12, 
    flexDirection: 'row', 
    width: '100%',
    backgroundColor: 'transparent', // Explicitly transparent
  },
  userRow: { justifyContent: 'flex-end' },
  botRow: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '80%',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    elevation: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  userBubble: {
    backgroundColor: '#007AFF',
    borderBottomRightRadius: 4,
  },
  botBubble: {
    backgroundColor: '#FFFFFF',
    borderBottomLeftRadius: 4,
  },
  messageText: { fontSize: 16, lineHeight: 22 },
  userText: { color: '#FFFFFF' },
  botText: { color: '#1C1C1E' },
  inputArea: {
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#E5E5EA',
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: '#F2F2F7',
    borderRadius: 24,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  input: {
    flex: 1,
    fontSize: 16,
    maxHeight: 100,
    paddingTop: 8,
    paddingBottom: 8,
    color: '#1C1C1E',
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
  sendButtonDisabled: { backgroundColor: '#C7C7CC' },
  contextBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#E5F1FF',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 8,
    marginLeft: 12,
  },
  contextText: { fontSize: 12, color: '#007AFF', fontWeight: '600' },
  actionContainer: { marginTop: 12, gap: 8 },
  actionButton: {
    backgroundColor: '#F2F2F7',
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: 'center',
  },
  actionButtonText: { color: '#007AFF', fontWeight: '600' },
  cancelButton: { backgroundColor: 'transparent' },
  cancelButtonText: { color: '#FF3B30' },
});