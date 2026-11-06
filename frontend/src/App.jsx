import { useState } from 'react';
import Login from './components/Login';
import MainForm from './components/MainForm';
import Summary from './components/Summary';
import FabTraveler from './components/fab/FabTraveler';
import './styles/App.css';

function App() {
  const [currentView, setCurrentView] = useState('login'); // 'login', 'main', 'summary'
  const [mode, setMode] = useState('synthesis'); // 'synthesis' | 'fab'
  const [userInfo, setUserInfo] = useState(null);
  const [sessionToken, setSessionToken] = useState(null);
  const [summaryMessage, setSummaryMessage] = useState('');
  const [summaryDetails, setSummaryDetails] = useState(null);

  const handleLoginSuccess = (user, token) => {
    setUserInfo(user);
    setSessionToken(token);
    setCurrentView('main');
  };

  const handleUploadSuccess = (message, summary) => {
    setSummaryMessage(message);
    setSummaryDetails(summary);
    setCurrentView('summary');
  };

  const handleAddMore = () => {
    setCurrentView('main');
    setSummaryMessage('');
    setSummaryDetails(null);
  };

  const handleLogout = () => {
    setUserInfo(null);
    setSessionToken(null);
    setSummaryMessage('');
    setSummaryDetails(null);
    localStorage.removeItem('sessionToken');
    setCurrentView('login');
  };

  return (
    <div className="app">
      <div className="container">
        {currentView === 'login' && (
          <Login onLoginSuccess={handleLoginSuccess} />
        )}

        {currentView === 'main' && userInfo && (
          <>
            <div className="mode-tabs">
              <button
                className={`mode-tab ${mode === 'synthesis' ? 'active' : ''}`}
                onClick={() => setMode('synthesis')}
              >
                Synthesis upload
              </button>
              <button
                className={`mode-tab ${mode === 'fab' ? 'active' : ''}`}
                onClick={() => setMode('fab')}
              >
                Fabrication traveler
              </button>
            </div>
            {mode === 'synthesis' ? (
              <MainForm userInfo={userInfo} onUploadSuccess={handleUploadSuccess} />
            ) : (
              <FabTraveler userInfo={userInfo} />
            )}
          </>
        )}

        {currentView === 'summary' && (
          <Summary
            message={summaryMessage}
            summary={summaryDetails}
            onAddMore={handleAddMore}
            onLogout={handleLogout}
          />
        )}
      </div>
    </div>
  );
}

export default App;
