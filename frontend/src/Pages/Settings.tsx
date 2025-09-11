import React, { useState, useEffect, useCallback } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { 
  Typography, 
  Button, 
  Dialog, 
  DialogActions, 
  DialogContent, 
  DialogTitle,
  TextField,
  Box,
  Stack,
  IconButton,
  Chip
} from '@mui/material';
import { 
  Add as AddIcon, 
  Delete as DeleteIcon, 
  Edit as EditIcon,
  Visibility as VisibilityIcon
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { useTablePageSize } from '../hooks/useTablePageSize';
import SearchBox from '../Components/SearchBox';

interface Tag {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  host_count: number;
}

interface TagWithHosts extends Tag {
  hosts: Array<{
    id: number;
    fqdn: string;
    ipv4: string;
    ipv6: string;
    active: boolean;
    status: string;
  }>;
}

const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [tags, setTags] = useState<Tag[]>([]);
  const [filteredTags, setFilteredTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTags, setSelectedTags] = useState<GridRowSelectionModel>([]);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [searchColumn, setSearchColumn] = useState<string>('name');
  
  // Add/Edit dialog state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [tagName, setTagName] = useState('');
  const [tagDescription, setTagDescription] = useState('');
  
  // View hosts dialog state
  const [viewHostsDialogOpen, setViewHostsDialogOpen] = useState(false);
  const [viewingTag, setViewingTag] = useState<TagWithHosts | null>(null);

  const { pageSize, pageSizeOptions } = useTablePageSize({
    reservedHeight: 350,
  });

  // Search columns configuration
  const searchColumns = [
    { field: 'name', label: t('tags.name', 'Name') },
    { field: 'description', label: t('tags.description', 'Description') }
  ];

  // Load tags from API
  const loadTags = useCallback(async () => {
    setLoading(true);
    try {
      const response = await window.fetch('/api/tags', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        setTags(data);
      } else {
        console.error('Failed to fetch tags');
      }
    } catch (error) {
      console.error('Error fetching tags:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Search functionality
  const performSearch = useCallback(() => {
    if (!searchTerm.trim()) {
      setFilteredTags(tags);
      return;
    }

    const filtered = tags.filter(tag => {
      const fieldValue = tag[searchColumn as keyof Tag];
      if (fieldValue === null || fieldValue === undefined) {
        return false;
      }
      return String(fieldValue).toLowerCase().includes(searchTerm.toLowerCase());
    });
    
    setFilteredTags(filtered);
  }, [searchTerm, searchColumn, tags]);

  // Update filtered data when tags change or search is cleared
  useEffect(() => {
    if (!searchTerm.trim()) {
      setFilteredTags(tags);
    } else {
      performSearch();
    }
  }, [tags, searchTerm, searchColumn, performSearch]);

  useEffect(() => {
    loadTags();
  }, [loadTags]);

  // Handle create tag
  const handleCreateTag = async () => {
    if (!tagName.trim()) return;
    
    try {
      const response = await window.fetch('/api/tags', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
        },
        body: JSON.stringify({
          name: tagName.trim(),
          description: tagDescription.trim() || null
        }),
      });
      
      if (response.ok) {
        await loadTags();
        setAddDialogOpen(false);
        setTagName('');
        setTagDescription('');
      } else {
        const error = await response.json();
        console.error('Failed to create tag:', error.detail);
        // TODO: Show user-friendly error message
      }
    } catch (error) {
      console.error('Error creating tag:', error);
    }
  };

  // Handle update tag
  const handleUpdateTag = async () => {
    if (!editingTag || !tagName.trim()) return;
    
    try {
      const response = await window.fetch(`/api/tags/${editingTag.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
        },
        body: JSON.stringify({
          name: tagName.trim(),
          description: tagDescription.trim() || null
        }),
      });
      
      if (response.ok) {
        await loadTags();
        setEditDialogOpen(false);
        setEditingTag(null);
        setTagName('');
        setTagDescription('');
      } else {
        const error = await response.json();
        console.error('Failed to update tag:', error.detail);
        // TODO: Show user-friendly error message
      }
    } catch (error) {
      console.error('Error updating tag:', error);
    }
  };

  // Handle delete tags
  const handleDeleteTags = async () => {
    if (selectedTags.length === 0) return;
    
    try {
      const deletePromises = selectedTags.map(id =>
        window.fetch(`/api/tags/${id}`, {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
          },
        })
      );
      
      await Promise.all(deletePromises);
      await loadTags();
      setSelectedTags([]);
    } catch (error) {
      console.error('Error deleting tags:', error);
    }
  };

  // Handle view hosts for tag
  const handleViewHosts = async (tagId: number) => {
    try {
      const response = await window.fetch(`/api/tags/${tagId}/hosts`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        setViewingTag(data);
        setViewHostsDialogOpen(true);
      } else {
        console.error('Failed to fetch tag hosts');
      }
    } catch (error) {
      console.error('Error fetching tag hosts:', error);
    }
  };

  // Handle edit tag
  const handleEditTag = (tag: Tag) => {
    setEditingTag(tag);
    setTagName(tag.name);
    setTagDescription(tag.description || '');
    setEditDialogOpen(true);
  };

  // DataGrid columns
  const columns: GridColDef[] = [
    { field: 'name', headerName: t('tags.name', 'Name'), width: 200 },
    { field: 'description', headerName: t('tags.description', 'Description'), width: 300, flex: 1 },
    { field: 'host_count', headerName: t('tags.hostCount', 'Host Count'), width: 120 },
    {
      field: 'updated_at',
      headerName: t('tags.lastUpdated', 'Last Updated'),
      width: 180,
      renderCell: (params) => new Date(params.value).toLocaleDateString()
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      width: 150,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <IconButton
            size="small"
            onClick={() => handleViewHosts(params.row.id)}
            title={t('tags.viewHosts', 'View Hosts')}
          >
            <VisibilityIcon />
          </IconButton>
          <IconButton
            size="small"
            onClick={() => handleEditTag(params.row)}
            title={t('common.edit', 'Edit')}
          >
            <EditIcon />
          </IconButton>
        </Box>
      ),
    },
  ];

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h4" sx={{ mb: 3 }}>
        {t('nav.settings', 'Settings')}
      </Typography>

      <Typography variant="h5" sx={{ mb: 2 }}>
        {t('tags.title', 'Tags')}
      </Typography>

      {/* Search Box */}
      <SearchBox
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        searchColumn={searchColumn}
        setSearchColumn={setSearchColumn}
        columns={searchColumns}
        placeholder={t('search.searchTags', 'Search tags')}
      />

      {/* Data Grid */}
      <div style={{ height: `${Math.min(600, Math.max(300, (pageSize + 2) * 52 + 120))}px`, width: '100%' }}>
        <DataGrid
          rows={filteredTags}
          columns={columns}
          loading={loading}
          checkboxSelection
          onRowSelectionModelChange={setSelectedTags}
          rowSelectionModel={selectedTags}
          initialState={{
            pagination: {
              paginationModel: { page: 0, pageSize: pageSize },
            },
          }}
          pageSizeOptions={pageSizeOptions}
        />
      </div>

      {/* Action Buttons */}
      <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setAddDialogOpen(true)}
        >
          {t('tags.addTag', 'Add Tag')}
        </Button>
        <Button
          variant="outlined"
          startIcon={<DeleteIcon />}
          onClick={handleDeleteTags}
          disabled={selectedTags.length === 0}
        >
          {t('common.delete', 'Delete')} ({selectedTags.length})
        </Button>
      </Stack>

      {/* Add Tag Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tags.addTag', 'Add Tag')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('tags.name', 'Name')}
            fullWidth
            variant="outlined"
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label={t('tags.description', 'Description')}
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={tagDescription}
            onChange={(e) => setTagDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
          <Button onClick={handleCreateTag} variant="contained">{t('common.add', 'Add')}</Button>
        </DialogActions>
      </Dialog>

      {/* Edit Tag Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tags.editTag', 'Edit Tag')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('tags.name', 'Name')}
            fullWidth
            variant="outlined"
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label={t('tags.description', 'Description')}
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={tagDescription}
            onChange={(e) => setTagDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
          <Button onClick={handleUpdateTag} variant="contained">{t('common.save', 'Save')}</Button>
        </DialogActions>
      </Dialog>

      {/* View Hosts Dialog */}
      <Dialog open={viewHostsDialogOpen} onClose={() => setViewHostsDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {t('tags.hostsAssociatedWith', 'Hosts associated with')} "{viewingTag?.name}"
        </DialogTitle>
        <DialogContent>
          {viewingTag?.hosts && viewingTag.hosts.length > 0 ? (
            <Box sx={{ mt: 1 }}>
              {viewingTag.hosts.map(host => (
                <Chip
                  key={host.id}
                  label={`${host.fqdn} (${host.ipv4})`}
                  variant="outlined"
                  sx={{ m: 0.5 }}
                  color={host.active ? 'primary' : 'default'}
                />
              ))}
            </Box>
          ) : (
            <Typography>{t('tags.noHostsAssociated', 'No hosts are associated with this tag.')}</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewHostsDialogOpen(false)}>{t('common.close', 'Close')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Settings;