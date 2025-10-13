const mockPost = jest.fn();
const mockGet = jest.fn();
const mockCreate = jest.fn(() => ({
  post: mockPost,
  get: mockGet,
}));

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: mockCreate,
  },
  create: mockCreate,
}));

describe('API client helpers', () => {
  beforeEach(() => {
    jest.resetModules();
    mockPost.mockReset();
    mockGet.mockReset();
    mockCreate.mockClear();
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  it('configures the axios client with the default base url when the environment variable is absent', async () => {
    await import('../api');

    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate).toHaveBeenCalledWith({
      baseURL: 'http://localhost:8000',
      headers: {
        'Content-Type': 'application/json',
      },
    });
  });

  it('configures the axios client with the provided base url and headers', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.com';

    await import('../api');

    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate).toHaveBeenCalledWith({
      baseURL: 'https://api.example.com',
      headers: {
        'Content-Type': 'application/json',
      },
    });
  });

  it('posts chat messages to the chat endpoint and returns the payload', async () => {
    const response = { role: 'assistant', content: 'Bonjour !' };
    mockPost.mockResolvedValueOnce({ data: response });

    const { sendChatMessage } = await import('../api');
    const result = await sendChatMessage('Salut');

    expect(mockPost).toHaveBeenCalledWith('/chat', { message: 'Salut' });
    expect(result).toEqual(response);
  });

  it('retrieves the WebRTC configuration', async () => {
    const response = { ice_servers: [{ urls: ['stun:stun.example.com'] }] };
    mockGet.mockResolvedValueOnce({ data: response });

    const { getWebRTCConfig } = await import('../api');
    const result = await getWebRTCConfig();

    expect(mockGet).toHaveBeenCalledWith('/webrtc/config');
    expect(result).toEqual(response);
  });

  it('creates a WebRTC session with the provided payload', async () => {
    const payload = { client_id: '123', offer_sdp: 'offer', metadata: { foo: 'bar' } };
    const response = { id: 'session-id' };
    mockPost.mockResolvedValueOnce({ data: response });

    const { createWebRTCSession } = await import('../api');
    const result = await createWebRTCSession(payload);

    expect(mockPost).toHaveBeenCalledWith('/webrtc/sessions', payload);
    expect(result).toEqual(response);
  });

  it('fetches an existing WebRTC session', async () => {
    const response = { id: 'session-42' };
    mockGet.mockResolvedValueOnce({ data: response });

    const { getWebRTCSession } = await import('../api');
    const result = await getWebRTCSession('session-42');

    expect(mockGet).toHaveBeenCalledWith('/webrtc/sessions/session-42');
    expect(result).toEqual(response);
  });

  it('submits a WebRTC answer for a session', async () => {
    const payload = { responder_id: 'responder', answer_sdp: 'answer' };
    const response = { id: 'session-42', answer_sdp: 'answer' };
    mockPost.mockResolvedValueOnce({ data: response });

    const { submitWebRTCAnswer } = await import('../api');
    const result = await submitWebRTCAnswer('session-42', payload);

    expect(mockPost).toHaveBeenCalledWith('/webrtc/sessions/session-42/answer', payload);
    expect(result).toEqual(response);
  });

  it('submits a WebRTC ICE candidate for a session', async () => {
    const payload = { candidate: { candidate: 'candidate-data' } };
    const response = { id: 'session-42', ice_candidates: [payload.candidate] };
    mockPost.mockResolvedValueOnce({ data: response });

    const { submitWebRTCCandidate } = await import('../api');
    const result = await submitWebRTCCandidate('session-42', payload);

    expect(mockPost).toHaveBeenCalledWith('/webrtc/sessions/session-42/candidates', payload);
    expect(result).toEqual(response);
  });
});
