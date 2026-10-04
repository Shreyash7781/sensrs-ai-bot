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

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: trimmedQuestion,
        }),
      });

      if (!response.ok) {
        throw new Error("Server returned an error");
      }

      const data = await response.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources || [],
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Sorry, I couldn't connect to the SEnSRS AI server. Please try again.",
          sources: [],
        },
      ]);
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

    <div className="demo-watermark">
  DEMO • SEnSRS WEBSITE
</div>
    <header className="site-header">
      <div className="logo-area">
        <div className="logo-mark">S</div>

        <div>
          <div className="logo-text">SEnSRS</div>
          <div className="logo-subtitle">
            Centre of Excellence • IIT Ropar
          </div>
        </div>
      </div>

      <nav>
        <span>Home</span>
        <span>About</span>
        <span>Services</span>
        <span>Research</span>
        <span>Opportunities</span>
        <span>Events</span>
        <span>Gallery</span>
        <span>Contact</span>
      </nav>
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
          <button>Explore SEnSRS</button>
          <button className="outline-btn">
            Contact Us
          </button>
        </div>
      </div>
    </section>

    <section className="features">

      <div className="feature-card">
        <div className="feature-icon">◈</div>
        <h2>Advanced Geospatial Technologies</h2>
        <p>
          Advanced geospatial technologies for monitoring,
          mapping and analysis.
        </p>
      </div>

      <div className="feature-card">
        <div className="feature-icon">⌁</div>
        <h2>Comprehensive Field Research</h2>
        <p>
          Field-based research and environmental assessment
          for sustainable development.
        </p>
      </div>

      <div className="feature-card">
        <div className="feature-icon">◎</div>
        <h2>Policy Engagement</h2>
        <p>
          Scientific research supporting responsible policy
          and environmental governance.
        </p>
      </div>

    </section>

    <section className="services-section">

      <div className="section-heading">
        <span>WHAT WE DO</span>
        <h2>Our Services</h2>
      </div>

      <div className="service-grid">

        <div className="service-card">
          <div className="service-image drone"></div>
          <h3>Drone Mapping & Surveying</h3>
        </div>

        <div className="service-card">
          <div className="service-image dgps"></div>
          <h3>DGPS Surveying</h3>
        </div>

        <div className="service-card">
          <div className="service-image water"></div>
          <h3>Bathymetry</h3>
        </div>

        <div className="service-card">
          <div className="service-image web"></div>
          <h3>Web Development</h3>
        </div>

        <div className="service-card">
          <div className="service-image dashboard"></div>
          <h3>Dashboard Development</h3>
        </div>

        <div className="service-card">
          <div className="service-image app"></div>
          <h3>App Development</h3>
        </div>

      </div>
    </section>

    {/* ================= YOUR ORIGINAL CHATBOT STARTS HERE ================= */}

    {isOpen &&  (
        <div className="chatbot">

          {/* Header */}
          <div className="chat-header">
            <div className="header-info">
              <div className="bot-avatar">S</div>

              <div>
                <h2>SEnSRS AI Assistant</h2>

                <div className="online-status">
                  <span className="status-dot"></span>
                  Online
                </div>
              </div>
            </div>

            <button
              onClick={clearChat}
              className="clear-button"
            >
              Clear
            </button>
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
                    SEnSRS AI
                  </div>

                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
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