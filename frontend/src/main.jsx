import { hydrateRoot } from 'react-dom/client';
import { Nav } from './Nav.jsx';
import './styles.css';

function readProps(root) {
  try {
    return JSON.parse(root.dataset.reactProps ?? '');
  } catch (error) {
    console.error('Unable to initialize React navigation: invalid properties.', error);
    return null;
  }
}

for (const root of document.querySelectorAll('[data-react-nav]')) {
  const props = readProps(root);
  if (props) {
    hydrateRoot(root, <Nav {...props} />, {
      onRecoverableError: (error) => console.error('React navigation hydration warning.', error),
    });
  }
}
