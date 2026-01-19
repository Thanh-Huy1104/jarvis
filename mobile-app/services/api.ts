import axios from 'axios';
import API_BASE_URL from '../config/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const sendMessage = async (message: string) => {
  try {
    const response = await apiClient.post('/mobile/chat', { message });
    return response.data;
  } catch (error) {
    console.error('Error sending message:', error);
    throw error;
  }
};

export const getNotes = async () => {
  try {
    const response = await apiClient.get('/mobile/notes');
    return response.data;
  } catch (error) {
    console.error('Error getting notes:', error);
    throw error;
  }
};

export const getCalendarEvents = async () => {
  try {
    const response = await apiClient.get('/mobile/calendar');
    return response.data;
  } catch (error) {
    console.error('Error getting calendar events:', error);
    throw error;
  }
};

export const createSection = async (sectionName: string, description?: string) => {
  try {
    const response = await apiClient.post('/mobile/notes/sections', { 
      user_id: 'default-user',
      name: sectionName,
      description 
    });
    return response.data;
  } catch (error) {
    console.error('Error creating section:', error);
    throw error;
  }
};
