import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ComplianceScore from '../components/ComplianceScore';

describe('ComplianceScore', () => {
  const baseProps = {
    score: 75,
    overallStatus: 'IN_PROGRESS',
    satisfiedCount: 6,
    totalCount: 8,
    missingCount: 1,
    conflictCount: 1,
  };

  it('renders the score percentage', () => {
    render(<ComplianceScore {...baseProps} />);
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('renders ACTION REQUIRED when not ready', () => {
    render(<ComplianceScore {...baseProps} />);
    expect(screen.getByText('ACTION REQUIRED')).toBeInTheDocument();
  });

  it('renders READY TO SUBMIT when status is READY', () => {
    render(<ComplianceScore {...baseProps} overallStatus="READY" />);
    expect(screen.getByText('READY TO SUBMIT')).toBeInTheDocument();
  });

  it('renders READY TO SUBMIT when score is 100', () => {
    render(<ComplianceScore {...baseProps} score={100} overallStatus="IN_PROGRESS" />);
    expect(screen.getByText('READY TO SUBMIT')).toBeInTheDocument();
  });

  it('displays requirement summary and stats labels', () => {
    render(<ComplianceScore {...baseProps} />);
    expect(screen.getByText(/6 of 8 requirements/)).toBeInTheDocument();
    expect(screen.getByText('Satisfied')).toBeInTheDocument();
    expect(screen.getByText('Missing')).toBeInTheDocument();
    expect(screen.getByText('Conflicts')).toBeInTheDocument();
  });

  it('handles null/undefined score safely (defaults to 0)', () => {
    render(<ComplianceScore {...baseProps} score={null} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('handles zero counts safely without crashing', () => {
    const { container } = render(
      <ComplianceScore
        {...baseProps}
        satisfiedCount={0}
        totalCount={0}
        missingCount={0}
        conflictCount={0}
      />
    );
    expect(container.querySelector('.bg-slate-900\\/70')).toBeInTheDocument();
    expect(screen.getByText(/0 of 0 requirements/)).toBeInTheDocument();
  });

  describe('auditor overrides', () => {
    it('shows "Auditor Overrides Active" when hasOverrides is true', () => {
      render(
        <ComplianceScore
          {...baseProps}
          hasOverrides={true}
          aiScore={60}
          adjustedScore={85}
        />
      );
      expect(screen.getByText('Auditor Overrides Active')).toBeInTheDocument();
    });

    it('displays AI and auditor-adjusted score labels when overrides are active', () => {
      render(
        <ComplianceScore
          {...baseProps}
          hasOverrides={true}
          aiScore={60}
          adjustedScore={85}
        />
      );
      expect(screen.getByText('AI Automated:')).toBeInTheDocument();
      expect(screen.getByText('Auditor-Adjusted:')).toBeInTheDocument();
    });

    it('does NOT show override badge when hasOverrides is false', () => {
      render(<ComplianceScore {...baseProps} />);
      expect(screen.queryByText('Auditor Overrides Active')).not.toBeInTheDocument();
    });

    it('uses adjustedScore as display score when overrides are active', () => {
      render(
        <ComplianceScore
          {...baseProps}
          score={50}
          hasOverrides={true}
          adjustedScore={90}
        />
      );
      expect(screen.getByText('90%')).toBeInTheDocument();
    });
  });
});
