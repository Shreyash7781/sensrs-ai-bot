import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const welcomeMessage = {
  role: "assistant",
  content:
    "Hello! I'm the SEnSRS AI Assistant. I can help you find information about SEnSRS services, internships, research, and programmes.",
  sources: [],
};

function App() {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const messagesEndRef = useRef(null);

  // Auto-scroll whenever messages/loading changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  // Listen for custom open event if dispatched from elsewhere
  useEffect(() => {
    const openChat = () => setIsOpen(true);
    window.addEventListener("open-sensrs-chat", openChat);
    return () => {
      window.removeEventListener("open-sensrs-chat", openChat);
    };
  }, []);



  const sendMessage = async () => {
    const trimmedQuestion = question.trim();

    if (!trimmedQuestion || loading) return;

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: trimmedQuestion,
        sources: [],
      },
    ]);

    setQuestion("");
    setLoading(true);

    let streamStarted = false;

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: trimmedQuestion,
          }),
        }
      );

      if (!response.ok) {
        throw new Error("Server returned an error");
      }

      const contentType =
        response.headers.get("content-type") || "";

      // Support existing non-streaming JSON responses too.
      if (contentType.includes("application/json")) {
        const data = await response.json();

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.answer,
            sources: data.sources || [],
          },
        ]);

        return;
      }

      if (!response.body) {
        throw new Error("Streaming is not supported by this response");
      }

      // Add an empty assistant message to fill progressively.
      streamStarted = true;

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
          sources: [],
        },
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const updateLastAssistant = (updater) => {
        setMessages((prev) => {
          const next = [...prev];

          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "assistant") {
              next[i] = updater(next[i]);
              break;
            }
          }

          return next;
        });
      };

      const processEvent = (line) => {
        if (!line.trim()) return;

        const event = JSON.parse(line);

        if (event.type === "chunk") {
          updateLastAssistant((message) => ({
            ...message,
            content: message.content + event.text,
          }));
        } else if (event.type === "done") {
          updateLastAssistant((message) => ({
            ...message,
            content: event.answer,
            sources: event.sources || [],
          }));
        } else if (event.type === "error") {
          updateLastAssistant((message) => ({
            ...message,
            content: event.message,
          }));
        }
      };

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          processEvent(line);
        }
      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        processEvent(buffer);
      }
    } catch (error) {
      const errorMessage =
        "Sorry, I couldn't connect to the SEnSRS AI server. Please try again.";

      if (streamStarted) {
        setMessages((prev) => {
          const next = [...prev];

          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "assistant") {
              next[i] = {
                ...next[i],
                content: errorMessage,
                sources: [],
              };
              break;
            }
          }

          return next;
        });
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: errorMessage,
            sources: [],
          },
        ]);
      }
    } finally {
      setLoading(false);
    }
  };


  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    setMessages([welcomeMessage]);
    setQuestion("");
    setLoading(false);
  };

  const useSuggestion = (text) => {
    setQuestion(text);
  };

  return (
  <div className="app">

    {/* ================= DUMMY SEnSRS WEBSITE ================= */}

    <header className="site-header">
      <div className="logo-area">
  <img
    src="/sensrs-logo.png"
    alt="SEnSRS - IIT Ropar"
    className="sensrs-logo"
  />
  <div>
    <div className="logo-text">SEnSRS</div>
    <div className="logo-subtitle">
      Centre of Excellence · IIT Ropar
    </div>
  </div>
</div>


    </header>

    <section className="hero">
      <div className="hero-content">
        <div className="hero-label">
          CENTRE OF EXCELLENCE
        </div>

        <h1>
          Socio-Environmental Sustainability
          <br />
          for River Sand-mining
        </h1>

        <p>
          Advancing scientific and technology-driven solutions
          for sustainable sand mining and environmental
          governance.
        </p>

        <div className="hero-buttons">
          <button
  onClick={() => {
    window.location.href = "https://sensrs.com/";
  }}
>
  Explore SEnSRS
</button>
          <button
  className="outline-btn"
  onClick={() => {
    window.location.href = "https://sensrs.com/contact/";
  }}
>
  Contact Us
</button>
        </div>
      </div>
    </section>



    <section className="services-section chatbot-about-section">
  <div className="section-heading">
    <span>YOUR AI ASSISTANT</span>
    <h2>Meet the SEnSRS AI Assistant</h2>
    <p className="chatbot-description">
      The SEnSRS AI Assistant is designed to help you quickly find
      information about the Centre of Excellence for Socio-Environmental
      Sustainability of River Sand Mining (SEnSRS) at IIT Ropar.
      Ask questions about research activities, internship opportunities,
      PhD programmes, services, and other initiatives. Powered by AI
      and information related to SEnSRS, it makes exploring the centre's
      work easier and more convenient.
    </p>

    <button
      className="primary-btn"
      onClick={() => setIsOpen(true)}
    >
      Ask the AI Assistant
    </button>
  </div>
</section>

    {/* ================= YOUR ORIGINAL CHATBOT STARTS HERE ================= */}

    {isOpen &&  (
        <div className="chatbot">

          {/* Header */}
          <div className="chat-header">
           <div className="header-info">
  <img
    src="/sensrs-logo.png"
    alt="SEnSRS Logo"
    className="chatbot-logo"
  />

              <div>
                <h2>SEnSRS AI Assistant</h2>

                <div className="online-status">
                  <span className="status-dot"></span>
                  Online
                </div>
              </div>
            </div>

            <div className="header-actions">
  <button
    onClick={clearChat}
    className="clear-button"
  >
    Clear
  </button>

  <button
    onClick={() => setIsOpen(false)}
    className="close-chat-button"
    aria-label="Close chatbot"
    title="Close chatbot"
  >
    ✕
  </button>
</div>
          </div>

          {/* Messages */}
          <div className="messages">

            {messages.map((message, index) => (
              <div
                key={index}
                className={`message-row ${message.role}`}
              >
                <div className={`message ${message.role}`}>

                  <div className="message-content">
                    {message.role === "assistant" ? (
                      <ReactMarkdown>
                        {message.content}
                      </ReactMarkdown>
                    ) : (
                      message.content
                    )}
                  </div>

                  {/* Source chips */}
                  {message.role === "assistant" &&
                    message.sources &&
                    message.sources.length > 0 && (
                      <div className="sources">
                        <div className="sources-title">
                          Sources
                        </div>

                        <div className="source-list">
  {message.sources.map((source, sourceIndex) => (
    <a
      key={`${source.title}-${sourceIndex}`}
      className="source"
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      📄 {source.title} ↗
    </a>
  ))}
</div>
                      </div>
                    )}
                </div>
              </div>
            ))}

            {/* Suggested questions */}
            {messages.length === 1 && !loading && (
              <div className="suggestions">
                <p>Try asking:</p>

                <button
                  onClick={() =>
                    useSuggestion(
                      "What services does SEnSRS provide?"
                    )
                  }
                >
                  What services does SEnSRS provide?
                </button>

                <button
                  onClick={() =>
                    useSuggestion(
                      "What internship opportunities does SEnSRS offer?"
                    )
                  }
                >
                  What internship opportunities are available?
                </button>

                <button
                  onClick={() =>
                    useSuggestion(
                      "What is the PhD programme at SEnSRS?"
                    )
                  }
                >
                  What is the PhD programme?
                </button>
              </div>
            )}

            {/* Typing indicator */}
            {loading && (
  <div className="message-row assistant">
    <div className="message assistant typing-message">
      <div className="typing-label">
        SEnSRS AI is typing...
      </div>

      <div
        className="typing-indicator"
        aria-label="SEnSRS AI is responding"
        role="status"
      >
        <span />
        <span />
        <span />
      </div>
    </div>
  </div>
)}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="input-area">
            <textarea
              value={question}
              onChange={(e) =>
                setQuestion(e.target.value)
              }
              onKeyDown={handleKeyDown}
              placeholder="Ask something about SEnSRS..."
              rows="1"
              disabled={loading}
            />

            <button
              onClick={sendMessage}
              disabled={!question.trim() || loading}
              aria-label="Send message"
            >
              ➤
            </button>
          </div>

          <div className="footer">
            Powered by SEnSRS AI
          </div>
        </div>
      )}

      {/* Floating button */}
      {!isOpen && (
  <div className="chat-whisper">
    Talk to SEnSRS AI
    <span className="whisper-arrow"></span>
  </div>
)}

<button
  className="chat-button"
  onClick={() => setIsOpen((prev) => !prev)}
  aria-label="Talk to SEnSRS AI"
>
  {isOpen ? "✕" : "💬"}
</button>
    </div>
  );
}

export default App;
