import { BrowserRouter } from 'react-router-dom';
import Approutes from './Routes/Approutes';
import { ToastProvider } from './components/Toast';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Approutes />
      </ToastProvider>
    </BrowserRouter>
  );
}

export default App;
