// ShadcnModals.jsx
import React from 'react';
import { 
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Button,
  Input,
  Label
} from './components/ui';

// Alert Modal (replacement for window.alert)
export const AlertModal = ({ isOpen, onClose, title, description }) => {
  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction>OK</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

// Confirm Modal (replacement for window.confirm)
export const ConfirmModal = ({ isOpen, onClose, onConfirm, title, description }) => {
  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Continue</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

// Prompt Modal (replacement for window.prompt)
export const PromptModal = ({ isOpen, onClose, onConfirm, title, description, defaultValue = "", label = "Input" }) => {
  const [value, setValue] = React.useState(defaultValue);
  
  React.useEffect(() => {
    if (isOpen) {
      setValue(defaultValue);
    }
  }, [isOpen, defaultValue]);
  
  const handleConfirm = () => {
    onConfirm(value);
    onClose();
  };
  
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {description}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="prompt-input" className="text-right">
              {label}
            </Label>
            <Input
              id="prompt-input"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
              className="col-span-3"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>
            Cancel
          </Button>
          <Button onClick={handleConfirm}>Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// Modal context provider
export const ModalContext = React.createContext({});

export const ModalProvider = ({ children }) => {
  const [alert, setAlert] = React.useState({
    isOpen: false,
    title: '',
    description: '',
    onClose: () => {},
  });
  
  const [confirm, setConfirm] = React.useState({
    isOpen: false,
    title: '',
    description: '',
    onConfirm: () => {},
    onClose: () => {},
  });
  
  const [prompt, setPrompt] = React.useState({
    isOpen: false,
    title: '',
    description: '',
    defaultValue: '',
    label: '',
    onConfirm: () => {},
    onClose: () => {},
  });
  
  // Alert function (replacement for window.alert)
  const showAlert = (title, description) => {
    return new Promise((resolve) => {
      setAlert({
        isOpen: true,
        title,
        description,
        onClose: () => {
          setAlert(prev => ({ ...prev, isOpen: false }));
          resolve();
        },
      });
    });
  };
  
  // Confirm function (replacement for window.confirm)
  const showConfirm = (title, description) => {
    return new Promise((resolve) => {
      setConfirm({
        isOpen: true,
        title,
        description,
        onConfirm: () => {
          setConfirm(prev => ({ ...prev, isOpen: false }));
          resolve(true);
        },
        onClose: () => {
          setConfirm(prev => ({ ...prev, isOpen: false }));
          resolve(false);
        },
      });
    });
  };
  
  // Prompt function (replacement for window.prompt)
  const showPrompt = (title, description, defaultValue = "", label = "Input") => {
    return new Promise((resolve) => {
      setPrompt({
        isOpen: true,
        title,
        description,
        defaultValue,
        label,
        onConfirm: (value) => {
          setPrompt(prev => ({ ...prev, isOpen: false }));
          resolve(value);
        },
        onClose: () => {
          setPrompt(prev => ({ ...prev, isOpen: false }));
          resolve(null);
        },
      });
    });
  };
  
  return (
    <ModalContext.Provider value={{ showAlert, showConfirm, showPrompt }}>
      {children}
      <AlertModal {...alert} />
      <ConfirmModal {...confirm} />
      <PromptModal {...prompt} />
    </ModalContext.Provider>
  );
};

// Custom hook to use the modal context
export const useModal = () => {
  const context = React.useContext(ModalContext);
  if (context === undefined) {
    throw new Error('useModal must be used within a ModalProvider');
  }
  return context;
};