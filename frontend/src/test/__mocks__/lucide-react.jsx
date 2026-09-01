// Shared lucide-react mock for all frontend tests
// vitest's mock system resolves named exports explicitly, so Proxy doesn't work

const iconStub = (name) => {
  const Component = (props) => <span data-testid={`icon-${name}`} {...props} />;
  Component.displayName = name;
  return Component;
};

// Export stubs for every icon used across the application
export const CheckCircle2 = iconStub('CheckCircle2');
export const AlertCircle = iconStub('AlertCircle');
export const AlertTriangle = iconStub('AlertTriangle');
export const XCircle = iconStub('XCircle');
export const FileText = iconStub('FileText');
export const ChevronDown = iconStub('ChevronDown');
export const ChevronUp = iconStub('ChevronUp');
export const Quote = iconStub('Quote');
export const ShieldCheck = iconStub('ShieldCheck');
export const ExternalLink = iconStub('ExternalLink');
export const BookOpen = iconStub('BookOpen');
export const Layers = iconStub('Layers');
export const Search = iconStub('Search');
export const Sparkles = iconStub('Sparkles');
export const ArrowRightLeft = iconStub('ArrowRightLeft');
export const HelpCircle = iconStub('HelpCircle');
export const X = iconStub('X');
export const Filter = iconStub('Filter');
export const ArrowUpDown = iconStub('ArrowUpDown');
export const RotateCcw = iconStub('RotateCcw');
export const UserCheck = iconStub('UserCheck');
export const Edit3 = iconStub('Edit3');
export const Trash2 = iconStub('Trash2');
export const Shield = iconStub('Shield');
export const CheckSquare = iconStub('CheckSquare');
export const Square = iconStub('Square');
export const MinusSquare = iconStub('MinusSquare');
export const MessageSquare = iconStub('MessageSquare');
export const CornerDownRight = iconStub('CornerDownRight');
export const Eye = iconStub('Eye');
export const Check = iconStub('Check');
export const ListChecks = iconStub('ListChecks');
export const ArrowRight = iconStub('ArrowRight');
export const Clock = iconStub('Clock');
export const AlertOctagon = iconStub('AlertOctagon');
export const Loader2 = iconStub('Loader2');
export const Undo2 = iconStub('Undo2');
export const Plus = iconStub('Plus');
export const LayoutDashboard = iconStub('LayoutDashboard');
export const LogOut = iconStub('LogOut');
export const User = iconStub('User');
export const RefreshCw = iconStub('RefreshCw');
export const Upload = iconStub('Upload');
export const Award = iconStub('Award');
export const History = iconStub('History');
export const BarChart3 = iconStub('BarChart3');
export const TrendingUp = iconStub('TrendingUp');
export const Minus = iconStub('Minus');
export const Users = iconStub('Users');
export const UserPlus = iconStub('UserPlus');
export const Calendar = iconStub('Calendar');
export const Square = iconStub('Square');
export const MinusSquare = iconStub('MinusSquare');
export const User = iconStub('User');
export const Bell = iconStub('Bell');
export const CheckCheck = iconStub('CheckCheck');

export default {};
