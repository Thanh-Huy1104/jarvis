import React, { useState } from 'react';
import { StyleSheet, TextInput, Button, FlatList, TouchableOpacity } from 'react-native';
import { Text, View } from '@/components/Themed';
import { sendMessage, createSection } from '../../services/api';

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

  const handleSendMessage = async () => {
    if (message.trim() === '') return;

    const userMessage: Message = { id: Date.now().toString(), text: message, sender: 'user' };
    setMessages(prevMessages => [...prevMessages, userMessage]);

    try {
      // If there's an active section, prepend it to the message
      const messageWithContext = activeSection 
        ? `Add note to ${activeSection}: ${message}`
        : message;
      
      const botResponse = await sendMessage(messageWithContext);
      
      // Check if response needs clarification
      if (botResponse.result?.needs_section_creation || botResponse.result?.needs_clarification) {
        const clarificationText = botResponse.result.clarification_question || botResponse.response;
        const botMessage: Message = { 
          id: Date.now().toString() + 'b', 
          text: clarificationText, 
          sender: 'bot',
          needsClarification: true,
          clarificationData: botResponse.result
        };
        setMessages(prevMessages => [...prevMessages, botMessage]);
        setPendingClarification(botResponse.result);
      } else {
        const botMessage: Message = { 
          id: Date.now().toString() + 'b', 
          text: botResponse.response, 
          sender: 'bot' 
        };
        setMessages(prevMessages => [...prevMessages, botMessage]);
        
        // Clear active section after successful note creation
        if (botResponse.result?.success) {
          setActiveSection(null);
        }
      }
    } catch (error) {
      const errorMessage: Message = { id: Date.now().toString() + 'e', text: 'Error sending message', sender: 'bot' };
      setMessages(prevMessages => [...prevMessages, errorMessage]);
    }

    setMessage('');
  };

  const handleYesNo = async (response: 'yes' | 'no') => {
    if (!pendingClarification) return;

    // Add user's response to messages
    const userMessage: Message = { 
      id: Date.now().toString(), 
      text: response === 'yes' ? 'Yes' : 'No', 
      sender: 'user' 
    };
    setMessages(prevMessages => [...prevMessages, userMessage]);

    // Handle the clarification response
    if (response === 'yes' && pendingClarification.needs_section_creation) {
      try {
        await createSection(pendingClarification.section_name);
        setActiveSection(pendingClarification.section_name); // Set active section
        const botMessage: Message = { 
          id: Date.now().toString() + 'b', 
          text: `Created section "${pendingClarification.section_name}". What would you like to note?`, 
          sender: 'bot' 
        };
        setMessages(prevMessages => [...prevMessages, botMessage]);
      } catch (error) {
        const botMessage: Message = { 
          id: Date.now().toString() + 'b', 
          text: 'Error creating section. Please try again.', 
          sender: 'bot' 
        };
        setMessages(prevMessages => [...prevMessages, botMessage]);
      }
    } else {
      const botMessage: Message = { 
        id: Date.now().toString() + 'b', 
        text: 'Okay, cancelled.', 
        sender: 'bot' 
      };
      setMessages(prevMessages => [...prevMessages, botMessage]);
    }

    setPendingClarification(null);
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={messages}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <View style={[styles.messageContainer, item.sender === 'user' ? styles.userMessage : styles.botMessage]}>
            <Text>{item.text}</Text>
            {item.needsClarification && (
              <View style={styles.clarificationButtons}>
                <TouchableOpacity 
                  style={[styles.button, styles.yesButton]} 
                  onPress={() => handleYesNo('yes')}
                >
                  <Text style={styles.buttonText}>Yes</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                  style={[styles.button, styles.noButton]} 
                  onPress={() => handleYesNo('no')}
                >
                  <Text style={styles.buttonText}>No</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}
      />
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={message}
          onChangeText={setMessage}
          placeholder="Type your message..."
        />
        <Button title="Send" onPress={handleSendMessage} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 10,
  },
  messageContainer: {
    padding: 10,
    borderRadius: 5,
    marginVertical: 5,
  },
  userMessage: {
    alignSelf: 'flex-end',
    backgroundColor: '#dcf8c6',
  },
  botMessage: {
    alignSelf: 'flex-start',
    backgroundColor: '#fff',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  input: {
    flex: 1,
    borderColor: '#ccc',
    borderWidth: 1,
    borderRadius: 5,
    padding: 10,
    marginRight: 10,
  },
  clarificationButtons: {
    flexDirection: 'row',
    marginTop: 10,
    gap: 10,
  },
  button: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 5,
    minWidth: 60,
    alignItems: 'center',
  },
  yesButton: {
    backgroundColor: '#4CAF50',
  },
  noButton: {
    backgroundColor: '#f44336',
  },
  buttonText: {
    color: 'white',
    fontWeight: 'bold',
  },
});
