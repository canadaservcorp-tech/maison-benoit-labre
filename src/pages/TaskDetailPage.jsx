import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';

const TaskDetailPage = () => {
  const { taskId } = useParams();
  const { isAdmin } = useAuth();
  const { t } = useLanguage();
  const [task, setTask] = useState(null);
  const [remarks, setRemarks] = useState([]);
  const [form, setForm] = useState({ status: '', hours_spent: '', cost_amount: '' });
  const [remarkMessage, setRemarkMessage] = useState('');
  const [error, setError] = useState('');

  const loadTask = async () => {
    try {
      const data = await apiFetch(`/api/tasks/${taskId}`);
      setTask(data.task);
      setForm({
        status: data.task.status,
        hours_spent: data.task.hours_spent || '',
        cost_amount: data.task.actual_cost || '',
      });
      const remarksData = await apiFetch(`/api/tasks/${taskId}/remarks`);
      setRemarks(remarksData.remarks || []);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadTask();
  }, [taskId]);

  const handleUpdate = async () => {
    try {
      await apiFetch(`/api/tasks/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          status: form.status,
          hours_spent: form.hours_spent ? Number(form.hours_spent) : null,
          actual_cost: form.cost_amount ? Number(form.cost_amount) : null,
        }),
      });
      await loadTask();
    } catch (err) {
      setError(err.message);
    }
  };

  const submitRemark = async () => {
    try {
      await apiFetch(`/api/tasks/${taskId}/remarks`, {
        method: 'POST',
        body: JSON.stringify({ message: remarkMessage }),
      });
      setRemarkMessage('');
      await loadTask();
    } catch (err) {
      setError(err.message);
    }
  };

  if (error) {
    return <div className="text-red-600">{error}</div>;
  }
  if (!task) {
    return <div className="text-gray-500">{t('loading')}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-xl font-semibold mb-2">{task.title}</h2>
        <p className="text-sm text-gray-500 mb-4">{task.description}</p>
        <div className="grid md:grid-cols-3 gap-4 text-sm">
          <div><span className="text-gray-500">{t('assignedTo')}: </span>{task.assigned_name}</div>
          <div><span className="text-gray-500">{t('dueDate')}: </span>{task.due_date || '-'}</div>
          <div><span className="text-gray-500">{t('category')}: </span>{task.category}</div>
          <div><span className="text-gray-500">{t('apartments')}: </span>{task.apartment_label || '-'}</div>
          <div><span className="text-gray-500">{t('areas')}: </span>{task.area_name || '-'}</div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
        <h3 className="font-semibold">{t('taskDetails')}</h3>
        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="text-sm text-gray-500">{t('status')}</label>
            <select
              value={form.status}
              onChange={(event) => setForm(prev => ({ ...prev, status: event.target.value }))}
              className="mt-1 w-full border rounded-lg px-2 py-1"
            >
              <option value="pending">{t('pending')}</option>
              <option value="in_progress">{t('inProgress')}</option>
              <option value="completed">{t('completed')}</option>
              <option value="cancelled">{t('cancelled')}</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-500">{t('hoursSpent')}</label>
            <input
              type="number"
              value={form.hours_spent}
              onChange={(event) => setForm(prev => ({ ...prev, hours_spent: event.target.value }))}
              className="mt-1 w-full border rounded-lg px-2 py-1"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500">{t('cost')}</label>
            <input
              type="number"
              value={form.cost_amount}
              onChange={(event) => setForm(prev => ({ ...prev, cost_amount: event.target.value }))}
              className="mt-1 w-full border rounded-lg px-2 py-1"
            />
          </div>
        </div>
        <button
          type="button"
          onClick={handleUpdate}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
        >
          {t('save')}
        </button>
        {!isAdmin && (
          <p className="text-xs text-gray-500">{t('remarks')}</p>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">{t('remarks')}</h3>
        <div className="space-y-3">
          {remarks.map(remark => (
            <div key={remark.id} className="border rounded-lg p-3">
              <p className="text-sm font-medium">{remark.author_name}</p>
              <p className="text-sm text-gray-600">{remark.message}</p>
            </div>
          ))}
          {remarks.length === 0 && <p className="text-sm text-gray-500">No remarks yet.</p>}
        </div>
        <div className="mt-4 space-y-2">
          <textarea
            value={remarkMessage}
            onChange={(event) => setRemarkMessage(event.target.value)}
            rows={3}
            className="w-full border rounded-lg px-3 py-2"
            placeholder={t('addRemark')}
          />
          <button
            type="button"
            onClick={submitRemark}
            disabled={!remarkMessage}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm disabled:bg-gray-400"
          >
            {t('addRemark')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default TaskDetailPage;
